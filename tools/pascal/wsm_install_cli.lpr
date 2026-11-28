{ SPDX-License-Identifier: LicenseRef-Volnist }

program wsm_install_cli;
{$mode objfpc}{$H+}

{ WSM installer — read-only front end, Free Pascal implementation.

  WHAT THIS IS
  ------------
  A compiled reimplementation of the part of `wsm_install/cli.py` that decides
  whether a hardware report is usable and whether the installer may proceed:
  argument parsing, report loading, schema-version selection, the structural
  preflight checks, and the exit codes. Its purpose is to show that the
  admission decision does not need a Python runtime before anyone rewrites the
  code that touches a disk.

  It is read-only by construction. This program:
    * opens the report for reading and closes it;
    * writes only to stdout and stderr;
    * never opens a block device, /proc, /sys, or any path other than the
      report named on the command line;
    * never spawns a process — there is no exec, fork, system or popen call in
      this source and no unit that provides one is used;
    * never asks for privileges and works as an unprivileged user.

  THE EXIT-CODE CONTRACT (identical to wsm_install/cli.py)
  -------------------------------------------------------
    0  the report was accepted (and, for --classify, the summary was printed).
       `--version` and `--help` also exit 0.
    2  refusal: bad arguments, unreadable report, invalid JSON, a declared
       schema version this tree cannot validate, or a structural schema error.
       Also `--execute`, which is disabled everywhere.
    3  the report is valid but required critical evidence is unresolved, so no
       plan is emitted. Only `--preflight` can return 3; `--classify` is
       diagnostic and returns 0 on the same report.

  WHAT IS DELIBERATELY NOT REPLICATED
  -----------------------------------
  Stated here because the honest scope of a port is part of the port.

  1. JSON Schema validation. The Python CLI loads schemas/*.schema.json and
     runs Draft202012Validator. This program has no schema library and does not
     read a schema file at all; it implements a fixed subset of the same rules
     in code (see CheckReport and friends). The subset is listed below. A
     report that violates only a rule outside the subset is accepted here and
     refused by Python — that is a fail-open difference, and it is the reason
     this binary is not yet a substitute for the Python front end.
     Implemented: required members; additionalProperties:false on the root,
     environment, platform, privacy, device, identity, driver, firmware,
     evidence and collectors-item objects; string minLength/maxLength on the
     fields that carry them; the report_id and PCI id patterns; the
     enumerated values for boot_mode, virtualization, category, bus,
     criticality, discovery_status, driver.status, firmware.requirement,
     firmware.runtime_status, evidence.kind, evidence.confidence,
     functional_tests.status, privacy.profile, collectors.scope and
     redactions_applied; the three `const false` privacy flags; the
     schema_version const for the selected version; a light ISO-8601 check for
     the `date-time` and `date` formats.
     Not implemented: `uniqueItems` on criticality (checked only for exact
     duplicates of strings), the `uri` format, the full RFC 3339 grammar,
     the cpu/gpu/network/storage/display/recommendations object interiors,
     pci_link, and additionalProperties on those nested objects.

  2. The draft plan document. `wsm_install/plan.py:build_plan` produces a
     canonical, digest-bearing `wsm-install-plan/1` document on stdout. This
     program does not build it. It does reproduce the *blocker* rules from
     build_plan, because those decide exit code 3; it does not reproduce the
     plan body, the plan_sha256 digest, or the device_summary. Consequence:
     stdout differs on a successful preflight. It does not change the exit
     code. On success this program prints a small
     `wsm-install-preflight/1` object instead, and says so on stderr.

  3. `--profile-evidence`, `--plan-output`, `--install`, `--guided`, `--tui`,
     `--check-env`, `--admission`, `--write-plan`, `--schema` and the
     `--target-*` options are refused with exit 2 rather than implemented. They
     belong to paths that either write a file or reach towards a disk, and
     refusing is the only honest answer this binary can give. `--execute` is
     refused with the same message the Python CLI prints.

  4. argparse's help text and its wrapping. `--help` prints a faithful but not
     byte-identical usage; the refusal *codes* match.

  5. One place where this program is STRICTER than Python: a GPU device that
     names exactly one half of `identity.vendor_id`/`identity.device_id` is
     refused here. JSON Schema cannot express "both or neither", so Python
     accepts it. The delta is one-directional — this program refuses more,
     never less — and it is recorded in scripts/check_fpc_cli_parity.py as a
     documented strictness rather than hidden.

  Contract owner: docs/INSTALLER-PREFLIGHT.md, wsm_install/cli.py,
  wsm_install/report_schema.py, wsm_install/plan.py. }

uses
  SysUtils, Classes, wsmjson;

const
  { Bytes, not a literal, so the file needs no particular source encoding. }
  EM_DASH = #$E2#$80#$94;

  EXIT_OK = 0;
  EXIT_REFUSED = 2;
  EXIT_BLOCKED = 3;

  VERSION_TEXT = 'wsm-install 0.1.0';

  MAX_SCHEMA_ERRORS = 20;

  SUPPORTED_VERSION_OLD = '1.0.0';
  SUPPORTED_VERSION_CURRENT = '1.1.0';

  PCI_ID_PATTERN = '^(0x)?[0-9a-fA-F]{4}$';

type
  TNameArray = array of string;
  TMode = (mPreflight, mClassify);

  TSubsystem = record
    Name: string;
    Categories: TNameArray;
  end;

var
  { Arguments. }
  GReportPath: string = '';
  GBackend: string = '';
  GWantVersion: Boolean = False;
  GWantHelp: Boolean = False;
  GPreflight: Boolean = False;
  GDryRun: Boolean = False;
  GClassify: Boolean = False;
  GQuiet: Boolean = False;
  GExecute: Boolean = False;
  GArgumentProblem: string = '';

  { Schema errors, in the order they were found. }
  GErrors: TStringList;
  GErrorCount: Integer = 0;

  { Warnings and blockers from the plan rules. }
  GWarnings: TStringList;
  GBlockers: TStringList;

{ ------------------------------------------------------------------ helpers }

function Names(const Values: array of string): TNameArray;
var
  Index: Integer;
begin
  SetLength(Result, Length(Values));
  for Index := 0 to High(Values) do
    Result[Index] := Values[Index];
end;

function IndexOfName(const List: TNameArray; const Name: string): Integer;
var
  Index: Integer;
begin
  for Index := 0 to High(List) do
    if List[Index] = Name then
      Exit(Index);
  Result := -1;
end;

function HasName(const List: TNameArray; const Name: string): Boolean;
begin
  Result := IndexOfName(List, Name) >= 0;
end;

{ Returns a new array with one more name. Dynamic-array Concat is not used so
  that this unit needs nothing from the generic helpers. }
function AppendName(const List: TNameArray; const Name: string): TNameArray;
var
  Index: Integer;
begin
  SetLength(Result, Length(List) + 1);
  for Index := 0 to High(List) do
    Result[Index] := List[Index];
  Result[High(Result)] := Name;
end;

function AppendNames(const List, Extra: TNameArray): TNameArray;
var
  Index: Integer;
begin
  Result := List;
  for Index := 0 to High(Extra) do
    Result := AppendName(Result, Extra[Index]);
end;

{ Python's `".".join(str(part) for part in path) or "$"`. }
function ChildPath(const Base, Name: string): string;
begin
  if Base = '$' then
    Result := Name
  else
    Result := Base + '.' + Name;
end;

function ItemPath(const Base: string; Index: Integer): string;
begin
  Result := Base + '.' + IntToStr(Index);
end;

function QuotedNames(const List: TNameArray): string;
var
  Index: Integer;
begin
  Result := '';
  for Index := 0 to High(List) do
  begin
    if Index > 0 then
      Result := Result + ', ';
    Result := Result + '''' + List[Index] + '''';
  end;
end;

procedure AddSchemaError(const Location, Message: string);
begin
  Inc(GErrorCount);
  if GErrors.Count < MAX_SCHEMA_ERRORS then
    GErrors.Add(Format('wsm-install: schema error at %s: %s', [Location, Message]));
end;

function TypeNameOf(Value: TWsmJson): string;
begin
  if Value = nil then
    Exit('null');
  case Value.Kind of
    jkNull: Result := 'null';
    jkFalse, jkTrue: Result := 'boolean';
    jkNumber:
      if Value.IsIntegerNumber then
        Result := 'integer'
      else
        Result := 'number';
    jkString: Result := 'string';
    jkArray: Result := 'array';
    jkObject: Result := 'object';
  else
    Result := 'null';
  end;
end;

function Repr(Value: TWsmJson): string;
begin
  if Value = nil then
    Result := 'None'
  else
    Result := Value.PythonRepr;
end;

{ ---- individual rule shapes, each mirroring one jsonschema keyword ---- }

function ValueIsObject(Value: TWsmJson; const Location: string): Boolean;
begin
  // Absent is not wrong: a property that is not there is valid, and requiredness is
  // RequireMembers' job. Without this, every optional object or array in a report —
  // `display`, `cpu` — made a valid document invalid.
  if Value = nil then
    Exit(True);
  Result := Value.IsObject;
  if not Result then
    AddSchemaError(Location, Format('%s is not of type ''object''', [Repr(Value)]));
end;

function ValueIsArray(Value: TWsmJson; const Location: string): Boolean;
begin
  // Absent is not wrong: a property that is not there is valid, and requiredness is
  // RequireMembers' job. Without this, every optional object or array in a report —
  // `display`, `cpu` — made a valid document invalid.
  if Value = nil then
    Exit(True);
  Result := Value.IsArray;
  if not Result then
    AddSchemaError(Location, Format('%s is not of type ''array''', [Repr(Value)]));
end;

{ An absent member is not a type error: JSON Schema says a property that is not present
  is valid, and requiredness is enforced separately by RequireMembers. Checking an
  optional member as if it were present made every report without `notes` invalid. }
function ValueIsString(Value: TWsmJson; const Location: string): Boolean;
begin
  if Value = nil then
    Exit(True);
  Result := Value.IsString;
  if not Result then
    AddSchemaError(Location, Format('%s is not of type ''string''', [Repr(Value)]));
end;

function ValueIsBoolean(Value: TWsmJson; const Location: string): Boolean;
begin
  if Value = nil then
    Exit(True);
  Result := Value.IsBoolean;
  if not Result then
    AddSchemaError(Location, Format('%s is not of type ''boolean''', [Repr(Value)]));
end;

function ValueIsInteger(Value: TWsmJson; const Location: string): Boolean;
begin
  if Value = nil then
    Exit(True);
  Result := Value.IsNumber and Value.IsIntegerNumber;
  if not Result then
    AddSchemaError(Location, Format('%s is not of type ''integer''', [Repr(Value)]));
end;

procedure RequireMembers(Value: TWsmJson; const Location: string; const Required: TNameArray);
var
  Index: Integer;
begin
  if (Value = nil) or (not Value.IsObject) then
    Exit;
  for Index := 0 to High(Required) do
    if not Value.HasMember(Required[Index]) then
      AddSchemaError(Location, Format('''%s'' is a required property', [Required[Index]]));
end;

procedure CheckAdditionalProperties(Value: TWsmJson; const Location: string;
  const Allowed: TNameArray);
var
  Index: Integer;
begin
  if (Value = nil) or (not Value.IsObject) then
    Exit;
  for Index := 0 to Value.Count - 1 do
    if not HasName(Allowed, Value.MemberName(Index)) then
      AddSchemaError(Location,
        Format('Additional properties are not allowed (''%s'' was unexpected)',
          [Value.MemberName(Index)]));
end;

procedure CheckEnum(Value: TWsmJson; const Location: string; const Allowed: TNameArray);
var
  Text: string;
begin
  if (Value = nil) or (not Value.IsString) then
    Exit;
  Text := Value.AsText;
  if not HasName(Allowed, Text) then
    AddSchemaError(Location,
      Format('%s is not one of [%s]', [Repr(Value), QuotedNames(Allowed)]));
end;

procedure CheckStringField(Value: TWsmJson; const Location: string;
  MinLength, MaxLength: Integer);
var
  Text: string;
begin
  if (Value = nil) or (not Value.IsString) then
    Exit;
  Text := Value.AsText;
  if (MinLength > 0) and (Length(Text) < MinLength) then
    AddSchemaError(Location, Format('%s is too short', [Repr(Value)]));
  if (MaxLength > 0) and (Length(Text) > MaxLength) then
    AddSchemaError(Location, Format('%s is too long', [Repr(Value)]));
end;

procedure CheckPattern(Value: TWsmJson; const Location: string;
  const Pattern: string; Matches: Boolean);
begin
  if (Value = nil) or (not Value.IsString) then
    Exit;
  if not Matches then
    AddSchemaError(Location, Format('%s does not match ''%s''', [Repr(Value), Pattern]));
end;

procedure CheckFalseConst(Value: TWsmJson; const Location: string);
begin
  if Value = nil then
    Exit;
  if not (Value.IsBoolean and (not Value.IsTrue)) then
    AddSchemaError(Location, 'False was expected');
end;

{ `^[A-Za-z0-9_-]+$` }
function MatchesReportIdPattern(const Text: string): Boolean;
var
  Index: Integer;
  Current: Char;
begin
  Result := Length(Text) > 0;
  for Index := 1 to Length(Text) do
  begin
    Current := Text[Index];
    if not ((Current in ['A'..'Z']) or (Current in ['a'..'z']) or
            (Current in ['0'..'9']) or (Current = '_') or (Current = '-')) then
      Exit(False);
  end;
end;

// `^(0x)?[0-9a-fA-F]{4}$` — a brace-comment would end at the `}` in the pattern.
function MatchesPciIdPattern(const Text: string): Boolean;
var
  Index, Start: Integer;
  Current: Char;
begin
  Result := False;
  if Length(Text) = 4 then
    Start := 1
  else if (Length(Text) = 6) and (Copy(Text, 1, 2) = '0x') then
    Start := 3
  else
    Exit;
  for Index := Start to Start + 3 do
  begin
    Current := Text[Index];
    if not ((Current in ['0'..'9']) or (Current in ['a'..'f']) or (Current in ['A'..'F'])) then
      Exit(False);
  end;
  Result := True;
end;

{ A deliberately light RFC 3339 shape: YYYY-MM-DDTHH:MM:SS with an optional
  fractional part and an optional Z or +HH:MM offset. Full grammar validation
  is not replicated; see the header. }
function LooksLikeDateTime(const Text: string): Boolean;
var
  Index: Integer;
  Digits: string;
begin
  if Length(Text) < 19 then
    Exit(False);
  if (Text[5] <> '-') or (Text[8] <> '-') then
    Exit(False);
  if not (Text[11] in ['T', 't', ' ']) then
    Exit(False);
  if (Text[14] <> ':') or (Text[17] <> ':') then
    Exit(False);
  Digits := Copy(Text, 1, 4) + Copy(Text, 6, 2) + Copy(Text, 9, 2) +
            Copy(Text, 12, 2) + Copy(Text, 15, 2) + Copy(Text, 18, 2);
  for Index := 1 to Length(Digits) do
    if not (Digits[Index] in ['0'..'9']) then
      Exit(False);
  Result := True;
end;

function LooksLikeDate(const Text: string): Boolean;
var
  Index: Integer;
begin
  Result := False;
  if Length(Text) <> 10 then
    Exit;
  if (Text[5] <> '-') or (Text[8] <> '-') then
    Exit;
  for Index := 1 to Length(Text) do
    if (Index <> 5) and (Index <> 8) and (not (Text[Index] in ['0'..'9'])) then
      Exit;
  Result := True;
end;

procedure CheckDateTime(Value: TWsmJson; const Location: string);
begin
  if (Value = nil) or (not Value.IsString) then
    Exit;
  if not LooksLikeDateTime(Value.AsText) then
    AddSchemaError(Location, Format('%s is not a ''date-time''', [Repr(Value)]));
end;

procedure CheckDate(Value: TWsmJson; const Location: string);
begin
  if (Value = nil) or (not Value.IsString) then
    Exit;
  if not LooksLikeDate(Value.AsText) then
    AddSchemaError(Location, Format('%s is not a ''date''', [Repr(Value)]));
end;

{ --------------------------------------------------- version selection ---- }

function SelectVersion(Report: TWsmJson; out Version: string): Boolean;
var
  Declared: string;
  DeclaredIsString: Boolean;
begin
  Version := '';
  Declared := 'None';
  DeclaredIsString := False;
  if (Report <> nil) and Report.IsObject and Report.HasMember('schema_version') then
  begin
    if Report.Member('schema_version').IsString then
    begin
      Declared := Report.Member('schema_version').AsText;
      DeclaredIsString := True;
    end
    else
      Declared := Report.Member('schema_version').PythonRepr;
  end;
  if Declared = SUPPORTED_VERSION_OLD then
  begin
    Version := SUPPORTED_VERSION_OLD;
    Exit(True);
  end;
  if Declared = SUPPORTED_VERSION_CURRENT then
  begin
    Version := SUPPORTED_VERSION_CURRENT;
    Exit(True);
  end;
  // Python formats the declared version with repr(): a string comes out quoted, and an
  // absent one comes out as None without quotes. The refusal is compared byte for byte,
  // so both spellings matter.
  if DeclaredIsString then
    WriteLn(StdErr, Format('wsm-install: unsupported hardware report schema ''%s''; supported: %s, %s',
      [Declared, SUPPORTED_VERSION_OLD, SUPPORTED_VERSION_CURRENT]))
  else
    WriteLn(StdErr, Format('wsm-install: unsupported hardware report schema None; supported: %s, %s',
      [SUPPORTED_VERSION_OLD, SUPPORTED_VERSION_CURRENT]));
  Result := False;
end;

{ ------------------------------------------------------------ the checks -- }

procedure CheckEvidenceItem(Item: TWsmJson; const Location: string);
var
  Allowed, Kinds, Confidences, Required: TNameArray;
begin
  if not ValueIsObject(Item, Location) then
    Exit;
  Allowed := Names(['confidence', 'kind', 'observed_at', 'reference', 'source',
                    'source_url', 'source_version', 'summary']);
  Required := Names(['kind', 'source', 'observed_at', 'confidence', 'summary']);
  CheckAdditionalProperties(Item, Location, Allowed);
  RequireMembers(Item, Location, Required);
  Confidences := Names(['confirmed', 'strong', 'limited', 'unknown']);
  CheckEnum(Item.Member('confidence'), ChildPath(Location, 'confidence'), Confidences);
  Kinds := Names(['live-observation', 'kernel-log', 'database-record',
                  'functional-test', 'manual-review', 'user-reported']);
  CheckEnum(Item.Member('kind'), ChildPath(Location, 'kind'), Kinds);
  CheckDateTime(Item.Member('observed_at'), ChildPath(Location, 'observed_at'));
  if ValueIsString(Item.Member('source'), ChildPath(Location, 'source')) then
    CheckStringField(Item.Member('source'), ChildPath(Location, 'source'), 1, 0);
  if ValueIsString(Item.Member('summary'), ChildPath(Location, 'summary')) then
    CheckStringField(Item.Member('summary'), ChildPath(Location, 'summary'), 1, 0);
  ValueIsString(Item.Member('reference'), ChildPath(Location, 'reference'));
  ValueIsString(Item.Member('source_url'), ChildPath(Location, 'source_url'));
  ValueIsString(Item.Member('source_version'), ChildPath(Location, 'source_version'));
end;

procedure CheckFunctionalTest(Item: TWsmJson; const Location: string);
var
  Allowed, Required, Statuses: TNameArray;
  Index: Integer;
  Refs: TWsmJson;
begin
  if not ValueIsObject(Item, Location) then
    Exit;
  Allowed := Names(['capability', 'evidence_refs', 'method', 'result', 'status',
                    'tested_at']);
  Required := Names(['capability', 'status']);
  CheckAdditionalProperties(Item, Location, Allowed);
  RequireMembers(Item, Location, Required);
  if ValueIsString(Item.Member('capability'), ChildPath(Location, 'capability')) then
    CheckStringField(Item.Member('capability'), ChildPath(Location, 'capability'), 1, 0);
  Statuses := Names(['passed', 'failed', 'partial', 'not-run', 'unsupported', 'unknown']);
  CheckEnum(Item.Member('status'), ChildPath(Location, 'status'), Statuses);
  Refs := Item.Member('evidence_refs');
  if (Refs <> nil) and ValueIsArray(Refs, ChildPath(Location, 'evidence_refs')) then
    for Index := 0 to Refs.Count - 1 do
      ValueIsString(Refs.Item(Index), ItemPath(ChildPath(Location, 'evidence_refs'), Index));
  ValueIsString(Item.Member('method'), ChildPath(Location, 'method'));
  ValueIsString(Item.Member('result'), ChildPath(Location, 'result'));
  CheckDateTime(Item.Member('tested_at'), ChildPath(Location, 'tested_at'));
end;

procedure CheckCollector(Item: TWsmJson; const Location: string);
var
  Allowed, Required, Scopes: TNameArray;
begin
  if not ValueIsObject(Item, Location) then
    Exit;
  Allowed := Names(['available', 'exit_code', 'name', 'notes', 'scope', 'source_url',
                    'version']);
  Required := Names(['name', 'available', 'scope']);
  CheckAdditionalProperties(Item, Location, Allowed);
  RequireMembers(Item, Location, Required);
  ValueIsBoolean(Item.Member('available'), ChildPath(Location, 'available'));
  ValueIsInteger(Item.Member('exit_code'), ChildPath(Location, 'exit_code'));
  if ValueIsString(Item.Member('name'), ChildPath(Location, 'name')) then
    CheckStringField(Item.Member('name'), ChildPath(Location, 'name'), 1, 0);
  ValueIsString(Item.Member('notes'), ChildPath(Location, 'notes'));
  Scopes := Names(['unprivileged-read-only', 'privileged-read-only', 'offline-database']);
  CheckEnum(Item.Member('scope'), ChildPath(Location, 'scope'), Scopes);
  ValueIsString(Item.Member('source_url'), ChildPath(Location, 'source_url'));
  ValueIsString(Item.Member('version'), ChildPath(Location, 'version'));
end;

procedure CheckIdentity(Device: TWsmJson; const Location: string);
var
  Identity: TWsmJson;
  Allowed: TNameArray;
  Ids: array[0..3] of string;
  Index: Integer;
  HasVendor, HasDevice: Boolean;
  Pair: TWsmJson;
begin
  Identity := Device.Member('identity');
  if Identity = nil then
    Exit;
  if not ValueIsObject(Identity, Location) then
    Exit;
  Allowed := Names(['class_id', 'device_id', 'local_path', 'manufacturer', 'modalias',
                    'model', 'revision', 'subsystem_device_id', 'subsystem_vendor_id',
                    'vendor_id']);
  CheckAdditionalProperties(Identity, Location, Allowed);

  Ids[0] := 'device_id';
  Ids[1] := 'subsystem_device_id';
  Ids[2] := 'subsystem_vendor_id';
  Ids[3] := 'vendor_id';
  for Index := 0 to 3 do
  begin
    if Identity.HasMember(Ids[Index]) then
    begin
      if ValueIsString(Identity.Member(Ids[Index]), ChildPath(Location, Ids[Index])) then
        CheckPattern(Identity.Member(Ids[Index]), ChildPath(Location, Ids[Index]),
          PCI_ID_PATTERN, MatchesPciIdPattern(Identity.Member(Ids[Index]).AsText));
    end;
  end;

  ValueIsString(Identity.Member('class_id'), ChildPath(Location, 'class_id'));
  ValueIsString(Identity.Member('local_path'), ChildPath(Location, 'local_path'));
  ValueIsString(Identity.Member('manufacturer'), ChildPath(Location, 'manufacturer'));
  ValueIsString(Identity.Member('modalias'), ChildPath(Location, 'modalias'));
  ValueIsString(Identity.Member('model'), ChildPath(Location, 'model'));
  ValueIsString(Identity.Member('revision'), ChildPath(Location, 'revision'));

  { The GPU identity pair. JSON Schema cannot say "both or neither", so this
    is the one rule that is stricter here than in the Python CLI. See the
    header, and the `half-gpu-identity-pair` case in the parity harness. }
  Pair := Device.Member('category');
  if (Pair <> nil) and Pair.IsString and (Pair.AsText = 'gpu') then
  begin
    HasVendor := Identity.HasMember('vendor_id') and Identity.Member('vendor_id').IsString;
    HasDevice := Identity.HasMember('device_id') and Identity.Member('device_id').IsString;
    if HasVendor <> HasDevice then
      AddSchemaError(Location,
        'the GPU identity pair is incomplete: vendor_id and device_id must be present together');
  end;
end;

procedure CheckDevice(Device: TWsmJson; const Location, Version: string);
var
  Allowed, Required, Categories, Buses, Discoveries, DriverStatuses,
  FirmwareRequirements, FirmwareRuntimes, Criticalities: TNameArray;
  Driver, Firmware, Evidence, Tests, Criticality: TWsmJson;
  Index: Integer;
  Names11: TNameArray;
begin
  if not ValueIsObject(Device, Location) then
    Exit;

  Allowed := Names(['bus', 'category', 'criticality', 'device_id', 'discovery_status',
                    'display', 'driver', 'evidence', 'firmware', 'functional_tests',
                    'identity', 'recommendations']);
  if Version = SUPPORTED_VERSION_CURRENT then
  begin
    Names11 := Names(['cpu', 'gpu', 'network', 'storage']);
    Allowed := AppendNames(Allowed, Names11);
  end;
  Required := Names(['device_id', 'category', 'bus', 'discovery_status', 'driver',
                     'firmware', 'functional_tests', 'evidence']);
  CheckAdditionalProperties(Device, Location, Allowed);
  RequireMembers(Device, Location, Required);

  { Properties, in the alphabetical order jsonschema's stable sort produces. }
  Buses := Names(['pci', 'usb', 'platform', 'acpi', 'cpu', 'virtio', 'mmc', 'nvme',
                  'scsi', 'i2c', 'spi', 'drm', 'edid', 'other', 'unknown']);
  CheckEnum(Device.Member('bus'), ChildPath(Location, 'bus'), Buses);

  Categories := Names(['cpu', 'motherboard', 'memory', 'storage-controller',
                       'storage-device', 'network', 'gpu', 'display', 'audio', 'input',
                       'bluetooth', 'usb-controller', 'camera', 'other']);
  CheckEnum(Device.Member('category'), ChildPath(Location, 'category'), Categories);

  if Version = SUPPORTED_VERSION_CURRENT then
  begin
    ValueIsObject(Device.Member('cpu'), ChildPath(Location, 'cpu'));
    ValueIsObject(Device.Member('gpu'), ChildPath(Location, 'gpu'));
    ValueIsObject(Device.Member('network'), ChildPath(Location, 'network'));
    ValueIsObject(Device.Member('storage'), ChildPath(Location, 'storage'));
  end;

  Criticality := Device.Member('criticality');
  if Criticality <> nil then
    if ValueIsArray(Criticality, ChildPath(Location, 'criticality')) then
    begin
      Criticalities := Names(['boot-path', 'storage-install-target', 'primary-display',
                              'network-installation', 'input', 'audio',
                              'suspend-resume', 'optional-peripheral']);
      for Index := 0 to Criticality.Count - 1 do
        CheckEnum(Criticality.Item(Index),
          ItemPath(ChildPath(Location, 'criticality'), Index), Criticalities);
    end;

  if ValueIsString(Device.Member('device_id'), ChildPath(Location, 'device_id')) then
    CheckStringField(Device.Member('device_id'), ChildPath(Location, 'device_id'), 1, 0);

  Discoveries := Names(['discovered', 'not-detected', 'unknown']);
  CheckEnum(Device.Member('discovery_status'), ChildPath(Location, 'discovery_status'),
    Discoveries);

  ValueIsObject(Device.Member('display'), ChildPath(Location, 'display'));

  Driver := Device.Member('driver');
  if (Driver <> nil) and ValueIsObject(Driver, ChildPath(Location, 'driver')) then
  begin
    Allowed := Names(['bound_driver', 'candidate', 'kernel_config_symbol', 'module',
                      'module_loaded', 'notes', 'status']);
    CheckAdditionalProperties(Driver, ChildPath(Location, 'driver'), Allowed);
    RequireMembers(Driver, ChildPath(Location, 'driver'), Names(['status']));
    DriverStatuses := Names(['bound', 'module-loaded-unbound', 'available-only',
                             'none-known', 'error', 'not-applicable', 'unknown']);
    CheckEnum(Driver.Member('status'), ChildPath(ChildPath(Location, 'driver'), 'status'),
      DriverStatuses);
    ValueIsString(Driver.Member('bound_driver'),
      ChildPath(ChildPath(Location, 'driver'), 'bound_driver'));
    ValueIsString(Driver.Member('candidate'),
      ChildPath(ChildPath(Location, 'driver'), 'candidate'));
    ValueIsString(Driver.Member('kernel_config_symbol'),
      ChildPath(ChildPath(Location, 'driver'), 'kernel_config_symbol'));
    ValueIsString(Driver.Member('module'), ChildPath(ChildPath(Location, 'driver'), 'module'));
    ValueIsBoolean(Driver.Member('module_loaded'),
      ChildPath(ChildPath(Location, 'driver'), 'module_loaded'));
    ValueIsString(Driver.Member('notes'), ChildPath(ChildPath(Location, 'driver'), 'notes'));
  end;

  Evidence := Device.Member('evidence');
  if (Evidence <> nil) and ValueIsArray(Evidence, ChildPath(Location, 'evidence')) then
    for Index := 0 to Evidence.Count - 1 do
      CheckEvidenceItem(Evidence.Item(Index),
        ItemPath(ChildPath(Location, 'evidence'), Index));

  Firmware := Device.Member('firmware');
  if (Firmware <> nil) and ValueIsObject(Firmware, ChildPath(Location, 'firmware')) then
  begin
    Allowed := Names(['files_observed', 'kernel_log_evidence', 'package_candidates',
                      'redistribution_status', 'requirement', 'runtime_status']);
    CheckAdditionalProperties(Firmware, ChildPath(Location, 'firmware'), Allowed);
    RequireMembers(Firmware, ChildPath(Location, 'firmware'),
      Names(['requirement', 'runtime_status']));
    FirmwareRequirements := Names(['required', 'optional', 'not-required', 'unknown']);
    CheckEnum(Firmware.Member('requirement'),
      ChildPath(ChildPath(Location, 'firmware'), 'requirement'), FirmwareRequirements);
    FirmwareRuntimes := Names(['loaded', 'available-not-confirmed-loaded', 'missing',
                               'load-error', 'not-needed', 'unknown']);
    CheckEnum(Firmware.Member('runtime_status'),
      ChildPath(ChildPath(Location, 'firmware'), 'runtime_status'), FirmwareRuntimes);
    ValueIsString(Firmware.Member('redistribution_status'),
      ChildPath(ChildPath(Location, 'firmware'), 'redistribution_status'));
  end;

  Tests := Device.Member('functional_tests');
  if (Tests <> nil) and ValueIsArray(Tests, ChildPath(Location, 'functional_tests')) then
    for Index := 0 to Tests.Count - 1 do
      CheckFunctionalTest(Tests.Item(Index),
        ItemPath(ChildPath(Location, 'functional_tests'), Index));

  CheckIdentity(Device, ChildPath(Location, 'identity'));

  ValueIsArray(Device.Member('recommendations'), ChildPath(Location, 'recommendations'));
end;

procedure CheckEnvironment(Environment: TWsmJson; const Location, Version: string);
var
  Allowed, Required, BootModes, Virtualizations: TNameArray;
  Platform: TWsmJson;
  PlatformAllowed: TNameArray;
  Index: Integer;
begin
  if not ValueIsObject(Environment, Location) then
    Exit;

  Allowed := Names(['architecture', 'boot_mode', 'kernel_release', 'kernel_version',
                    'platform', 'virtualization']);
  if Version = SUPPORTED_VERSION_CURRENT then
    Allowed := AppendName(Allowed, 'boot_mode_evidence');
  Required := Names(['architecture', 'kernel_release', 'boot_mode', 'virtualization']);
  CheckAdditionalProperties(Environment, Location, Allowed);
  RequireMembers(Environment, Location, Required);

  if ValueIsString(Environment.Member('architecture'), ChildPath(Location, 'architecture')) then
    CheckStringField(Environment.Member('architecture'),
      ChildPath(Location, 'architecture'), 1, 0);

  BootModes := Names(['uefi', 'bios', 'unknown']);
  CheckEnum(Environment.Member('boot_mode'), ChildPath(Location, 'boot_mode'), BootModes);

  if Version = SUPPORTED_VERSION_CURRENT then
    if ValueIsString(Environment.Member('boot_mode_evidence'),
      ChildPath(Location, 'boot_mode_evidence')) then
      CheckStringField(Environment.Member('boot_mode_evidence'),
        ChildPath(Location, 'boot_mode_evidence'), 1, 0);

  if ValueIsString(Environment.Member('kernel_release'),
    ChildPath(Location, 'kernel_release')) then
    CheckStringField(Environment.Member('kernel_release'),
      ChildPath(Location, 'kernel_release'), 1, 0);

  ValueIsString(Environment.Member('kernel_version'), ChildPath(Location, 'kernel_version'));

  Platform := Environment.Member('platform');
  if Platform <> nil then
    if ValueIsObject(Platform, ChildPath(Location, 'platform')) then
    begin
      PlatformAllowed := Names(['bios_date', 'bios_vendor', 'bios_version', 'board_name',
                                'board_vendor', 'board_version', 'product_name',
                                'system_vendor']);
      if Version = SUPPORTED_VERSION_CURRENT then
        PlatformAllowed := AppendName(PlatformAllowed, 'bios_release');
      CheckAdditionalProperties(Platform, ChildPath(Location, 'platform'), PlatformAllowed);
      CheckDate(Platform.Member('bios_date'),
        ChildPath(ChildPath(Location, 'platform'), 'bios_date'));
      // TNameArray is a dynamic array, not a TStringList: it has Length, not Count.
      for Index := 0 to Length(PlatformAllowed) - 1 do
        if PlatformAllowed[Index] <> 'bios_date' then
          ValueIsString(Platform.Member(PlatformAllowed[Index]),
            ChildPath(ChildPath(Location, 'platform'), PlatformAllowed[Index]));
    end;

  Virtualizations := Names(['none-detected', 'kvm', 'qemu', 'vmware', 'hyper-v', 'xen',
                            'container', 'other', 'unknown']);
  CheckEnum(Environment.Member('virtualization'), ChildPath(Location, 'virtualization'),
    Virtualizations);
end;

procedure CheckPrivacy(Privacy: TWsmJson; const Location: string);
var
  Allowed, Required, Profiles, Redactions: TNameArray;
  Items: TWsmJson;
  Index: Integer;
begin
  if not ValueIsObject(Privacy, Location) then
    Exit;
  Allowed := Names(['network_requests_performed', 'network_upload_performed', 'profile',
                    'redactions_applied', 'sensitive_identifiers_included']);
  Required := Names(['profile', 'network_upload_performed',
                     'sensitive_identifiers_included', 'network_requests_performed']);
  CheckAdditionalProperties(Privacy, Location, Allowed);
  RequireMembers(Privacy, Location, Required);

  CheckFalseConst(Privacy.Member('network_requests_performed'),
    ChildPath(Location, 'network_requests_performed'));
  CheckFalseConst(Privacy.Member('network_upload_performed'),
    ChildPath(Location, 'network_upload_performed'));
  Profiles := Names(['strict-local', 'sanitized-export', 'custom']);
  CheckEnum(Privacy.Member('profile'), ChildPath(Location, 'profile'), Profiles);
  Items := Privacy.Member('redactions_applied');
  if (Items <> nil) and ValueIsArray(Items, ChildPath(Location, 'redactions_applied')) then
  begin
    Redactions := Names(['serial-number', 'mac-address', 'uuid', 'hostname', 'username',
                         'ip-address', 'storage-wwn', 'other']);
    for Index := 0 to Items.Count - 1 do
      CheckEnum(Items.Item(Index),
        ItemPath(ChildPath(Location, 'redactions_applied'), Index), Redactions);
  end;
  CheckFalseConst(Privacy.Member('sensitive_identifiers_included'),
    ChildPath(Location, 'sensitive_identifiers_included'));
end;

procedure CheckStringArray(Value: TWsmJson; const Location: string);
var
  Index: Integer;
begin
  if Value = nil then
    Exit;
  if not ValueIsArray(Value, Location) then
    Exit;
  for Index := 0 to Value.Count - 1 do
    ValueIsString(Value.Item(Index), ItemPath(Location, Index));
end;

procedure CheckReport(Report: TWsmJson; const Version: string);
var
  Allowed, Required: TNameArray;
  Devices, Collectors, SchemaVersion: TWsmJson;
  Index: Integer;
begin
  Allowed := Names(['collected_at', 'collectors', 'devices', 'environment',
                    'limitations', 'privacy', 'report_id', 'schema_version', 'warnings']);
  Required := Names(['schema_version', 'report_id', 'collected_at', 'environment',
                     'collectors', 'devices', 'privacy']);

  { jsonschema visits `type`, then `additionalProperties`, then `required`, then
    `properties`; errors at the same path keep that order. }
  if not ValueIsObject(Report, '$') then
    Exit;
  CheckAdditionalProperties(Report, '$', Allowed);
  RequireMembers(Report, '$', Required);

  CheckDateTime(Report.Member('collected_at'), ChildPath('$', 'collected_at'));

  Collectors := Report.Member('collectors');
  if (Collectors <> nil) and ValueIsArray(Collectors, ChildPath('$', 'collectors')) then
    for Index := 0 to Collectors.Count - 1 do
      CheckCollector(Collectors.Item(Index),
        ItemPath(ChildPath('$', 'collectors'), Index));

  Devices := Report.Member('devices');
  if (Devices <> nil) and ValueIsArray(Devices, ChildPath('$', 'devices')) then
    for Index := 0 to Devices.Count - 1 do
      CheckDevice(Devices.Item(Index), ItemPath(ChildPath('$', 'devices'), Index), Version);

  if Report.HasMember('environment') then
    CheckEnvironment(Report.Member('environment'), ChildPath('$', 'environment'), Version);

  CheckStringArray(Report.Member('limitations'), ChildPath('$', 'limitations'));

  if Report.HasMember('privacy') then
    CheckPrivacy(Report.Member('privacy'), ChildPath('$', 'privacy'));

  if ValueIsString(Report.Member('report_id'), ChildPath('$', 'report_id')) then
  begin
    CheckStringField(Report.Member('report_id'), ChildPath('$', 'report_id'), 16, 80);
    CheckPattern(Report.Member('report_id'), ChildPath('$', 'report_id'),
      '^[A-Za-z0-9_-]+$', MatchesReportIdPattern(Report.Member('report_id').AsText));
  end;

  SchemaVersion := Report.Member('schema_version');
  if (SchemaVersion <> nil) and SchemaVersion.IsString and (SchemaVersion.AsText <> Version) then
    AddSchemaError(ChildPath('$', 'schema_version'),
      Format('%s was expected', ['''' + Version + '''']));

  CheckStringArray(Report.Member('warnings'), ChildPath('$', 'warnings'));
end;

{ --------------------------------------------------- plan rules (exit 3) -- }

function TextMember(Value: TWsmJson; const Name, Fallback: string): string;
var
  Item: TWsmJson;
begin
  Result := Fallback;
  if (Value = nil) or (not Value.IsObject) then
    Exit;
  Item := Value.Member(Name);
  if (Item <> nil) and Item.IsString then
    Result := Item.AsText;
end;

function BoolText(Value: TWsmJson): string;
begin
  if Value = nil then
    Result := 'unknown'
  else if Value.IsTrue then
    Result := 'true'
  else if Value.IsBoolean then
    Result := 'false'
  else
    Result := Value.PythonRepr;
end;

function HasCriticalRole(Device: TWsmJson): Boolean;
const
  REQUIRED_ROLES: array[0..2] of string = ('boot-path', 'primary-display', 'input');
var
  Criticality: TWsmJson;
  Index, Scan: Integer;
begin
  Result := False;
  Criticality := Device.Member('criticality');
  if (Criticality = nil) or (not Criticality.IsArray) then
    Exit;
  for Index := 0 to Criticality.Count - 1 do
    if Criticality.Item(Index).IsString then
      for Scan := 0 to High(REQUIRED_ROLES) do
        if Criticality.Item(Index).AsText = REQUIRED_ROLES[Scan] then
          Result := True;
end;

function HasRole(Device: TWsmJson; const Role: string): Boolean;
var
  Criticality: TWsmJson;
  Index: Integer;
begin
  Result := False;
  Criticality := Device.Member('criticality');
  if (Criticality = nil) or (not Criticality.IsArray) then
    Exit;
  for Index := 0 to Criticality.Count - 1 do
    if Criticality.Item(Index).IsString and (Criticality.Item(Index).AsText = Role) then
      Result := True;
end;

function HasPassedNetworkTest(Device: TWsmJson): Boolean;
var
  Tests: TWsmJson;
  Index: Integer;
  Capability, Status: string;
begin
  Result := False;
  Tests := Device.Member('functional_tests');
  if (Tests = nil) or (not Tests.IsArray) then
    Exit;
  for Index := 0 to Tests.Count - 1 do
  begin
    Capability := TextMember(Tests.Item(Index), 'capability', '');
    Status := TextMember(Tests.Item(Index), 'status', '');
    if (Status = 'passed') and ((Capability = 'network-link') or
       (Capability = 'network-connectivity')) then
      Result := True;
  end;
end;

procedure AddWarningUnique(const Text: string);
begin
  if GWarnings.IndexOf(Text) < 0 then
    GWarnings.Add(Text);
end;

{ Mirrors wsm_install/plan.py:build_plan's blocker and warning rules. The plan
  body itself is not built; only what decides exit code 3. }
procedure EvaluatePlanRules(Report: TWsmJson);
var
  Devices, ReportWarnings: TWsmJson;
  Device: TWsmJson;
  Index: Integer;
  Discovery, Requirement, Runtime, DeviceId: string;
  Roles: array[0..2] of string;
  RoleIndex: Integer;
  Observed: Boolean;
begin
  GWarnings.Add('no verified hardware profile evidence for this machine; ' +
                'the plan remains diagnostic-only');

  Devices := Report.Member('devices');
  if (Devices <> nil) and Devices.IsArray then
    for Index := 0 to Devices.Count - 1 do
    begin
      Device := Devices.Item(Index);
      if (Device = nil) or (not Device.IsObject) then
        Continue;
      DeviceId := TextMember(Device, 'device_id', '?');
      Discovery := TextMember(Device, 'discovery_status', 'unknown');
      if HasCriticalRole(Device) and ((Discovery = 'unknown') or (Discovery = 'not-detected')) then
        GBlockers.Add(Format('%s: required critical device discovery is %s',
          [DeviceId, Discovery]));
      Requirement := TextMember(Device.Member('firmware'), 'requirement', 'unknown');
      Runtime := TextMember(Device.Member('firmware'), 'runtime_status', 'unknown');
      if (Requirement = 'required') and ((Runtime = 'missing') or (Runtime = 'load-error')) then
      begin
        if HasCriticalRole(Device) then
          GBlockers.Add(Format('%s: required runtime firmware is %s', [DeviceId, Runtime]))
        else
          AddWarningUnique(Format('%s: required runtime firmware is %s', [DeviceId, Runtime]));
      end;
      if HasRole(Device, 'network-installation') and (not HasPassedNetworkTest(Device)) then
        AddWarningUnique(Format('%s: network installation path is not functionally tested; ' +
          'offline installation may be required', [DeviceId]));
    end;

  ReportWarnings := Report.Member('warnings');
  if (ReportWarnings <> nil) and ReportWarnings.IsArray then
    for Index := 0 to ReportWarnings.Count - 1 do
      if ReportWarnings.Item(Index).IsString then
        AddWarningUnique(ReportWarnings.Item(Index).AsText);

  Roles[0] := 'boot-path';
  Roles[1] := 'input';
  Roles[2] := 'primary-display';
  for RoleIndex := 0 to High(Roles) do
  begin
    Observed := False;
    if (Devices <> nil) and Devices.IsArray then
      for Index := 0 to Devices.Count - 1 do
        if HasRole(Devices.Item(Index), Roles[RoleIndex]) then
          Observed := True;
    if not Observed then
      AddWarningUnique(Format('required role ''%s'' is not represented in the report; ' +
        'plan remains diagnostic-only', [Roles[RoleIndex]]));
  end;

  GWarnings.Add('storage target is not selected by hardware discovery; explicit user ' +
                'selection and immediate identity revalidation are still required');
end;

{ ------------------------------------------------------- human summary ---- }

procedure ReportWarningsJoin(Report: TWsmJson; Lines: TStringList); forward;

function SummarizeReport(Report: TWsmJson): string;
var
  Environment, Devices, Device, Identity, Tests, Evidence: TWsmJson;
  Index, TestIndex, Discovered, UnknownCount: Integer;
  Lines: TStringList;
  LabelText, TestSummary, Provenance: string;
  DeviceTotal: Integer;
begin
  Lines := TStringList.Create;
  try
    Environment := Report.Member('environment');
    Devices := Report.Member('devices');
    Discovered := 0;
    UnknownCount := 0;
    DeviceTotal := 0;
    if (Devices <> nil) and Devices.IsArray then
      for Index := 0 to Devices.Count - 1 do
      begin
        Device := Devices.Item(Index);
        if TextMember(Device, 'discovery_status', '') = 'discovered' then
          Inc(Discovered)
        else if TextMember(Device, 'discovery_status', '') = 'unknown' then
          Inc(UnknownCount);
      end;

    Lines.Add('WSM hardware preflight ' + EM_DASH + ' report ' +
              TextMember(Report, 'report_id', 'unknown'));
    Lines.Add(Format('Schema: %s | collected: %s',
      [TextMember(Report, 'schema_version', 'unknown'),
       TextMember(Report, 'collected_at', 'unknown')]));
    Lines.Add(Format('Environment: %s | kernel %s | boot %s | virtualization %s',
      [TextMember(Environment, 'architecture', 'unknown'),
       TextMember(Environment, 'kernel_release', 'unknown'),
       TextMember(Environment, 'boot_mode', 'unknown'),
       TextMember(Environment, 'virtualization', 'unknown')]));
    if (Devices <> nil) and Devices.IsArray then
      DeviceTotal := Devices.Count;
    Lines.Add(Format('Devices: %d total, %d discovered, %d unknown',
      [DeviceTotal, Discovered, UnknownCount]));

    if (Devices <> nil) and Devices.IsArray then
      for Index := 0 to Devices.Count - 1 do
      begin
        Device := Devices.Item(Index);
        Identity := Device.Member('identity');
        LabelText := TextMember(Identity, 'model', '');
        if LabelText = '' then
          LabelText := TextMember(Identity, 'manufacturer', '');
        if LabelText = '' then
          LabelText := TextMember(Device, 'device_id', '?');

        TestSummary := '';
        Tests := Device.Member('functional_tests');
        if (Tests <> nil) and Tests.IsArray then
          for TestIndex := 0 to Tests.Count - 1 do
          begin
            if TestSummary <> '' then
              TestSummary := TestSummary + ', ';
            TestSummary := TestSummary +
              TextMember(Tests.Item(TestIndex), 'capability', 'unknown') + '=' +
              TextMember(Tests.Item(TestIndex), 'status', 'unknown');
          end;
        if TestSummary = '' then
          TestSummary := 'none';

        Evidence := Device.Member('evidence');
        if (Evidence <> nil) and Evidence.IsArray and (Evidence.Count > 0) then
          Provenance := Format('source=%s @ %s (%s)',
            [TextMember(Evidence.Item(0), 'source', 'unknown'),
             TextMember(Evidence.Item(0), 'observed_at', 'unknown'),
             TextMember(Evidence.Item(0), 'confidence', 'unknown')])
        else
          Provenance := 'source=unknown';

        Lines.Add(Format('- %s: %s; discovery=%s; driver=%s; firmware=%s; tests=[%s]; %s',
          [TextMember(Device, 'category', 'unknown'), LabelText,
           TextMember(Device, 'discovery_status', 'unknown'),
           TextMember(Device.Member('driver'), 'status', 'unknown'),
           TextMember(Device.Member('firmware'), 'runtime_status', 'unknown'),
           TestSummary, Provenance]));
      end;

    ReportWarningsJoin(Report, Lines);

    Result := Lines.Text;
    { TStringList.Text ends with a line break; the caller prints it as one block. }
    while (Length(Result) > 0) and (Result[Length(Result)] = #10) do
      Delete(Result, Length(Result), 1);
  finally
    Lines.Free;
  end;
end;

procedure ReportWarningsJoin(Report: TWsmJson; Lines: TStringList);
var
  Warnings: TWsmJson;
  Index: Integer;
  Joined: string;
begin
  Warnings := Report.Member('warnings');
  if (Warnings = nil) or (not Warnings.IsArray) or (Warnings.Count = 0) then
    Exit;
  Joined := '';
  for Index := 0 to Warnings.Count - 1 do
  begin
    if Joined <> '' then
      Joined := Joined + '; ';
    Joined := Joined + Warnings.Item(Index).AsText;
  end;
  Lines.Add('Report warnings: ' + Joined);
end;

{ --------------------------------------------------------- classification -- }
{ A faithful port of wsm_install/classification.py:classify. It is diagnostic
  only — the Python module decides no install readiness and neither does this
  one. It is here because `--classify` must answer the same way, and because a
  front end that cannot summarise the evidence it just validated is not much of
  a front end. }

var
  GSubsystems: array of TSubsystem;

procedure InitSubsystems;
begin
  SetLength(GSubsystems, 11);
  GSubsystems[0].Name := 'cpu';
  GSubsystems[0].Categories := Names(['cpu']);
  GSubsystems[1].Name := 'memory';
  GSubsystems[1].Categories := Names(['memory']);
  GSubsystems[2].Name := 'storage';
  GSubsystems[2].Categories := Names(['storage-controller', 'storage-device']);
  GSubsystems[3].Name := 'graphics';
  GSubsystems[3].Categories := Names(['gpu', 'display']);
  GSubsystems[4].Name := 'network';
  GSubsystems[4].Categories := Names(['network']);
  GSubsystems[5].Name := 'audio';
  GSubsystems[5].Categories := Names(['audio']);
  GSubsystems[6].Name := 'bluetooth';
  GSubsystems[6].Categories := Names(['bluetooth']);
  GSubsystems[7].Name := 'input';
  GSubsystems[7].Categories := Names(['input']);
  GSubsystems[8].Name := 'usb';
  GSubsystems[8].Categories := Names(['usb-controller']);
  GSubsystems[9].Name := 'camera';
  GSubsystems[9].Categories := Names(['camera']);
  GSubsystems[10].Name := 'other';
  GSubsystems[10].Categories := Names(['other']);
end;

function EvidenceStateFor(Device: TWsmJson): string;
var
  Discovery, Status, Bound, Candidate: string;
  Driver: TWsmJson;
begin
  Discovery := TextMember(Device, 'discovery_status', 'unknown');
  if Discovery = 'not-detected' then
    Exit('not-detected');
  if Discovery <> 'discovered' then
    Exit('unknown');

  Driver := Device.Member('driver');
  if (Driver = nil) or (not Driver.IsObject) then
    Exit('unknown');

  Status := TextMember(Driver, 'status', 'unknown');
  Bound := Trim(TextMember(Driver, 'bound_driver', ''));
  Candidate := Trim(TextMember(Driver, 'candidate', ''));

  if Status = 'bound' then
  begin
    { The collector represents built-in drivers by bound_driver even with no
      module symlink, so requiring `module` here would invent unknowns. }
    if Bound <> '' then
      Exit('driver-bound-not-tested')
    else
      Exit('unknown');
  end;
  if (Status = 'available-only') and (Candidate <> '') then
    Exit('candidate-only');
  if (Status = 'unknown') or (Status = 'error') then
    Exit('unknown');
  Result := 'not-tested';
end;

function FunctionalTestEvidenceState(const ReportedStatus: string): string;
begin
  if ReportedStatus = 'passed' then
    Result := 'supported-tested'
  else if ReportedStatus = 'failed' then
    Result := 'known-problem'
  else if ReportedStatus = 'not-run' then
    Result := 'not-tested'
  else
    Result := 'unknown';
end;

function CopySelected(Source: TWsmJson; const Wanted: TNameArray): TWsmJson;
var
  Index: Integer;
  Value: TWsmJson;
begin
  Result := TWsmJson.NewObject;
  if (Source = nil) or (not Source.IsObject) then
    Exit;
  for Index := 0 to High(Wanted) do
  begin
    Value := Source.Member(Wanted[Index]);
    if Value <> nil then
      Result.AddMember(Wanted[Index], Value.Clone);
  end;
end;

function DeviceEvidenceFor(Device: TWsmJson): TWsmJson;
var
  Evidence: TWsmJson;
begin
  Result := TWsmJson.NewObject;
  Result.AddMember('device_id', TWsmJson.NewString(TextMember(Device, 'device_id', '?')));
  if Device.Member('driver') <> nil then
    Result.AddMember('driver', CopySelected(Device.Member('driver'),
      Names(['status', 'candidate', 'module', 'module_loaded', 'bound_driver',
             'kernel_config_symbol', 'notes'])));
  if Device.Member('firmware') <> nil then
    Result.AddMember('firmware', CopySelected(Device.Member('firmware'),
      Names(['requirement', 'runtime_status', 'files_observed', 'package_candidates',
             'kernel_log_evidence', 'redistribution_status'])));
  Evidence := Device.Member('evidence');
  if (Evidence <> nil) and Evidence.IsArray then
    Result.AddMember('evidence', Evidence.Clone);
end;

function DevicesFor(Report: TWsmJson; const Categories: TNameArray): TWsmJson;
var
  Devices, Device, Category: TWsmJson;
  Index: Integer;
begin
  Result := TWsmJson.NewArray;
  Devices := Report.Member('devices');
  if (Devices = nil) or (not Devices.IsArray) then
    Exit;
  for Index := 0 to Devices.Count - 1 do
  begin
    Device := Devices.Item(Index);
    if (Device = nil) or (not Device.IsObject) then
      Continue;
    Category := Device.Member('category');
    if (Category <> nil) and Category.IsString and
       HasName(Categories, Category.AsText) then
      Result.AddItem(Device.Clone);
  end;
end;

{ Appends one item per functional test to a flat array, at capability scope.
  A passing capability never rolls up to a device-level PASS. }
procedure AppendFunctionalTestEvidence(Device: TWsmJson; Into: TWsmJson);
var
  Tests, Item, CopyValue: TWsmJson;
  Index: Integer;
  DeviceId: string;
begin
  DeviceId := TextMember(Device, 'device_id', '?');
  Tests := Device.Member('functional_tests');
  if (Tests = nil) or (not Tests.IsArray) then
    Exit;
  for Index := 0 to Tests.Count - 1 do
  begin
    if not Tests.Item(Index).IsObject then
      Continue;
    Item := TWsmJson.NewObject;
    Item.AddMember('device_id', TWsmJson.NewString(DeviceId));
    Item.AddMember('capability', TWsmJson.NewString(
      TextMember(Tests.Item(Index), 'capability', 'unknown')));
    Item.AddMember('reported_status', TWsmJson.NewString(
      TextMember(Tests.Item(Index), 'status', 'unknown')));
    Item.AddMember('evidence_state', TWsmJson.NewString(
      FunctionalTestEvidenceState(TextMember(Tests.Item(Index), 'status', 'unknown'))));
    CopyValue := Tests.Item(Index).Member('tested_at');
    if CopyValue <> nil then
      Item.AddMember('tested_at', CopyValue.Clone);
    CopyValue := Tests.Item(Index).Member('method');
    if CopyValue <> nil then
      Item.AddMember('method', CopyValue.Clone);
    CopyValue := Tests.Item(Index).Member('result');
    if CopyValue <> nil then
      Item.AddMember('result', CopyValue.Clone);
    CopyValue := Tests.Item(Index).Member('evidence_refs');
    if CopyValue <> nil then
      Item.AddMember('evidence_refs', CopyValue.Clone);
    Into.AddItem(Item);
  end;
end;

{ Does any observed device in these categories report a failed capability? }
function HasFailedCapability(Report: TWsmJson; const Categories: TNameArray): Boolean;
var
  Devices, Device, Tests, Category: TWsmJson;
  Index, TestIndex: Integer;
begin
  Result := False;
  Devices := Report.Member('devices');
  if (Devices = nil) or (not Devices.IsArray) then
    Exit;
  for Index := 0 to Devices.Count - 1 do
  begin
    Device := Devices.Item(Index);
    if (Device = nil) or (not Device.IsObject) then
      Continue;
    Category := Device.Member('category');
    if (Category = nil) or (not Category.IsString) or
       (not HasName(Categories, Category.AsText)) then
      Continue;
    Tests := Device.Member('functional_tests');
    if (Tests = nil) or (not Tests.IsArray) then
      Continue;
    for TestIndex := 0 to Tests.Count - 1 do
      if TextMember(Tests.Item(TestIndex), 'status', 'unknown') = 'failed' then
        Result := True;
  end;
end;

function ClassifySubsystem(Report: TWsmJson; const Subsystem: TSubsystem): TWsmJson;
var
  Devices, Device, Reasons, Identifiers, States, Tests, EvidenceList: TWsmJson;
  Index: Integer;
  State: string;
  AllBoundOrCandidate: Boolean;
begin
  Result := TWsmJson.NewObject;
  Devices := DevicesFor(Report, Subsystem.Categories);
  try
    Identifiers := TWsmJson.NewArray;
    States := TWsmJson.NewArray;
    Reasons := TWsmJson.NewArray;
    Tests := TWsmJson.NewArray;
    EvidenceList := TWsmJson.NewArray;
    AllBoundOrCandidate := Devices.Count > 0;

    if Devices.Count = 0 then
      Reasons.AddItem(TWsmJson.NewString(
        'no device record is present; report v1 has no coverage manifest, ' +
        'so absence cannot be interpreted as not-detected or not-collected'));

    for Index := 0 to Devices.Count - 1 do
    begin
      Device := Devices.Item(Index);
      Identifiers.AddItem(TWsmJson.NewString(TextMember(Device, 'device_id', '?')));
      State := EvidenceStateFor(Device);
      States.AddItem(TWsmJson.NewString(State));
      Reasons.AddItem(TWsmJson.NewString(Format('%s: %s',
        [TextMember(Device, 'device_id', '?'), State])));
      AppendFunctionalTestEvidence(Device, Tests);
      EvidenceList.AddItem(DeviceEvidenceFor(Device));
      if (State <> 'driver-bound-not-tested') and (State <> 'candidate-only') then
        AllBoundOrCandidate := False;
    end;

    { A summary can be `known` only if every observed device has a concrete
      driver binding or candidate, and no observed capability failed. }
    if (Devices.Count > 0) and AllBoundOrCandidate and
       (not HasFailedCapability(Report, Subsystem.Categories)) then
      Result.AddMember('level', TWsmJson.NewString('known'))
    else
      Result.AddMember('level', TWsmJson.NewString('unknown'));

    Result.AddMember('subsystem', TWsmJson.NewString(Subsystem.Name));
    Result.AddMember('devices', Identifiers);
    Result.AddMember('reasons', Reasons);
    { Schema v1 has no per-subsystem coverage manifest: always unknown. }
    Result.AddMember('coverage', TWsmJson.NewString('unknown'));
    if Devices.Count > 0 then
      Result.AddMember('observation', TWsmJson.NewString('device-records-present'))
    else
      Result.AddMember('observation', TWsmJson.NewString('no-device-record'));
    Result.AddMember('evidence_states', States);
    Result.AddMember('functional_tests', Tests);
    Result.AddMember('device_evidence', EvidenceList);
  finally
    Devices.Free;
  end;
end;

function ClassifyReport(Report: TWsmJson): TWsmJson;
var
  Subsystems, Counts: TWsmJson;
  Index, Known, UnknownCount: Integer;
  Verdict: TWsmJson;
  Level: TWsmJson;
begin
  Result := TWsmJson.NewObject;
  Subsystems := TWsmJson.NewArray;
  Known := 0;
  UnknownCount := 0;
  for Index := 0 to High(GSubsystems) do
  begin
    Verdict := ClassifySubsystem(Report, GSubsystems[Index]);
    Subsystems.AddItem(Verdict);
    Level := Verdict.Member('level');
    if (Level <> nil) and (Level.AsText = 'known') then
      Inc(Known)
    else
      Inc(UnknownCount);
  end;

  Counts := TWsmJson.NewObject;
  Counts.AddMember('certified', TWsmJson.NewNumber('0'));
  Counts.AddMember('known', TWsmJson.NewNumber(IntToStr(Known)));
  Counts.AddMember('unknown', TWsmJson.NewNumber(IntToStr(UnknownCount)));

  Result.AddMember('schema', TWsmJson.NewString('wsm-hardware-classification/2'));
  Result.AddMember('subsystems', Subsystems);
  Result.AddMember('counts', Counts);
  Result.AddMember('decision_policy',
    TWsmJson.NewString('docs/INSTALL-CAPABILITY-MATRIX.md'));
  Result.AddMember('note', TWsmJson.NewString(
    'Diagnostic summary only. Report v1 has no complete coverage manifest; ' +
    'functional-test results apply only to their named capability. This ' +
    'summary does not choose an installation scenario or authorize a plan.'));
end;

{ ------------------------------------------------------------- arguments -- }

const
  USAGE_TEXT =
    'usage: wsm-install [-h] [--version] [--preflight] --report PATH ' +
    '--backend {guix} [--dry-run] [--quiet] [--classify]' + LineEnding +
    LineEnding +
    'Validate a local WSM hardware report (read-only).' + LineEnding +
    LineEnding +
    'options:' + LineEnding +
    '  -h, --help       show this help message and exit' + LineEnding +
    '  --version        show program''s version number and exit' + LineEnding +
    '  --preflight      run report preflight' + LineEnding +
    '  --report PATH    hardware report JSON' + LineEnding +
    '  --backend {guix} only supported first-preview backend: guix -> guix-system' + LineEnding +
    '  --dry-run        required; never deploys or writes disks' + LineEnding +
    '  --quiet          suppress human summary' + LineEnding +
    '  --classify       print a read-only evidence summary; does not decide ' +
    'install readiness' + LineEnding;

  HELP_TEXT =
    USAGE_TEXT + LineEnding +
    'This is the Free Pascal front end. It implements the read-only preflight' + LineEnding +
    'and --classify only. --install, --guided, --tui, --check-env, --admission,' + LineEnding +
    '--plan-output, --profile-evidence, --write-plan, --schema and the' + LineEnding +
    '--target-* options are refused with exit code 2: they either write a file' + LineEnding +
    'or reach towards a disk. See docs/FPC-INSTALL-CLI.md.' + LineEnding;

var
  GMissingValueFor: string = '';

function NeedsValue(const Name: string): Boolean;
begin
  Result := (Name = '--report') or (Name = '--backend') or (Name = '--schema') or
            (Name = '--profile-evidence') or (Name = '--plan-output') or
            (Name = '--target-disk') or (Name = '--target-size-bytes') or
            (Name = '--firmware') or (Name = '--filesystem') or
            (Name = '--mount-point') or (Name = '--system-file') or
            (Name = '--write-plan') or (Name = '--acknowledge-disk');
end;

function IsRefusedOption(const Name: string): Boolean;
begin
  Result := (Name = '--install') or (Name = '--guided') or (Name = '--tui') or
            (Name = '--check-env') or (Name = '--admission') or
            (Name = '--write-plan') or (Name = '--plan-output') or
            (Name = '--profile-evidence') or (Name = '--schema') or
            (Name = '--target-disk') or (Name = '--target-size-bytes') or
            (Name = '--firmware') or (Name = '--filesystem') or
            (Name = '--mount-point') or (Name = '--system-file') or
            (Name = '--acknowledge-disk');
end;

{ Parses argv into the globals above. Returns False when the caller must stop
  immediately: an unknown option or a missing value is an argparse-style
  refusal, exit code 2. }
function ParseArguments: Boolean;
var
  Index: Integer;
  Argument, Name, InlineValue, Value: string;
  Separator: Integer;
begin
  Result := True;
  Index := 1;
  while Index <= ParamCount do
  begin
    Argument := ParamStr(Index);
    Name := Argument;
    InlineValue := '';
    Separator := Pos('=', Argument);
    if Separator > 0 then
    begin
      Name := Copy(Argument, 1, Separator - 1);
      InlineValue := Copy(Argument, Separator + 1, Length(Argument));
    end;

    if NeedsValue(Name) then
    begin
      if InlineValue <> '' then
        Value := InlineValue
      else
      begin
        Inc(Index);
        if Index > ParamCount then
        begin
          GMissingValueFor := Name;
          WriteLn(StdErr, 'usage: wsm-install [-h] [--version] [--preflight] ' +
                          '--report PATH --backend {guix} [--dry-run]');
          WriteLn(StdErr, Format('wsm-install: error: argument %s: expected one argument',
            [Name]));
          Exit(False);
        end;
        Value := ParamStr(Index);
      end;

      if Name = '--report' then
        GReportPath := Value
      else if Name = '--backend' then
        GBackend := Value
      else if IsRefusedOption(Name) then
        if GArgumentProblem = '' then
          GArgumentProblem := Format(
            'wsm-install: not-implemented-in-fpc: %s is refused by the Free Pascal ' +
            'front end; it is part of a path that writes a file or reaches a disk. ' +
            'Use the Python front end for it, or remove the option.', [Name]);
    end
    else if (Name = '--version') or (Name = '-h') or (Name = '--help') or
            (Name = '--preflight') or (Name = '--dry-run') or (Name = '--classify') or
            (Name = '--quiet') or (Name = '--execute') or
            ((Name = '--install') or (Name = '--guided') or (Name = '--tui') or
             (Name = '--check-env') or (Name = '--admission')) then
    begin
      if Name = '--version' then
        GWantVersion := True
      else if (Name = '-h') or (Name = '--help') then
        GWantHelp := True
      else if Name = '--preflight' then
        GPreflight := True
      else if Name = '--dry-run' then
        GDryRun := True
      else if Name = '--classify' then
        GClassify := True
      else if Name = '--quiet' then
        GQuiet := True
      else if Name = '--execute' then
        GExecute := True
      else if (GArgumentProblem = '') then
        GArgumentProblem := Format(
          'wsm-install: not-implemented-in-fpc: %s is refused by the Free Pascal ' +
          'front end; it is part of a path that writes a file or reaches a disk. ' +
          'Use the Python front end for it, or remove the option.', [Name]);
    end
    else
    begin
      WriteLn(StdErr, 'usage: wsm-install [-h] [--version] [--preflight] ' +
                      '--report PATH --backend {guix} [--dry-run]');
      WriteLn(StdErr, Format('wsm-install: error: unrecognized arguments: %s', [Argument]));
      Exit(False);
    end;

    Inc(Index);
  end;
end;

{ --------------------------------------------------------------- reading -- }

function ReadReportFile(const Path: string; out Text: string; out Error: string): Boolean;
var
  Stream: TFileStream;
begin
  Result := False;
  Text := '';
  Error := '';
  try
    Stream := TFileStream.Create(Path, fmOpenRead or fmShareDenyNone);
    try
      SetLength(Text, Stream.Size);
      if Stream.Size > 0 then
        Stream.ReadBuffer(Text[1], Stream.Size);
    finally
      Stream.Free;
    end;
    Result := True;
  except
    on E: Exception do
    begin
      Text := '';
      Error := E.Message;
    end;
  end;
end;

{ ------------------------------------------------------- preflight result -- }

function BuildPreflightResult(Report: TWsmJson; const Version: string): TWsmJson;
var
  Warnings, Blockers: TWsmJson;
  Index: Integer;
begin
  Result := TWsmJson.NewObject;
  Result.AddMember('schema', TWsmJson.NewString('wsm-install-preflight/1'));
  Result.AddMember('status', TWsmJson.NewString('accepted'));
  Result.AddMember('report_id', TWsmJson.NewString(TextMember(Report, 'report_id', 'unknown')));
  Result.AddMember('schema_version', TWsmJson.NewString(Version));
  Result.AddMember('plan_emitted', TWsmJson.NewBoolean(False));
  Result.AddMember('plan_note', TWsmJson.NewString(
    'the Free Pascal front end validates the report and evaluates the plan ' +
    'blockers; it does not build the wsm-install-plan/1 document, which is ' +
    'wsm_install/plan.py''s output. See docs/FPC-INSTALL-CLI.md.'));
  Warnings := TWsmJson.NewArray;
  for Index := 0 to GWarnings.Count - 1 do
    Warnings.AddItem(TWsmJson.NewString(GWarnings[Index]));
  Result.AddMember('warnings', Warnings);
  Blockers := TWsmJson.NewArray;
  for Index := 0 to GBlockers.Count - 1 do
    Blockers.AddItem(TWsmJson.NewString(GBlockers[Index]));
  Result.AddMember('blockers', Blockers);
end;

{ ------------------------------------------------------------------ main -- }

function Run: Integer;
var
  Source, LoadError, Version: string;
  Report, Document: TWsmJson;
  Index: Integer;
  Parsed: Boolean;
begin
  GErrors := TStringList.Create;
  GWarnings := TStringList.Create;
  GBlockers := TStringList.Create;
  InitSubsystems;
  try
    Parsed := ParseArguments;
    if not Parsed then
      Exit(EXIT_REFUSED);

    { argparse exits while parsing, before it checks required arguments. }
    if GWantVersion then
    begin
      WriteLn(VERSION_TEXT);
      Exit(EXIT_OK);
    end;
    if GWantHelp then
    begin
      Write(HELP_TEXT);
      Exit(EXIT_OK);
    end;

    if GReportPath = '' then
    begin
      WriteLn(StdErr, 'usage: wsm-install [-h] [--version] [--preflight] ' +
                      '--report PATH --backend {guix} [--dry-run]');
      WriteLn(StdErr, 'wsm-install: error: the following arguments are required: --report');
      Exit(EXIT_REFUSED);
    end;
    if GBackend = '' then
    begin
      WriteLn(StdErr, 'usage: wsm-install [-h] [--version] [--preflight] ' +
                      '--report PATH --backend {guix} [--dry-run]');
      WriteLn(StdErr, 'wsm-install: error: the following arguments are required: --backend');
      Exit(EXIT_REFUSED);
    end;
    if GBackend <> 'guix' then
    begin
      WriteLn(StdErr, 'usage: wsm-install [-h] [--version] [--preflight] ' +
                      '--report PATH --backend {guix} [--dry-run]');
      WriteLn(StdErr, Format('wsm-install: error: argument --backend: invalid choice: ' +
        '''%s'' (choose from ''guix'')', [GBackend]));
      Exit(EXIT_REFUSED);
    end;

    if GExecute then
    begin
      WriteLn(StdErr, 'wsm-install: execute.apply-disabled: --execute is disabled before ' +
                      'frontend selection or report processing');
      Exit(EXIT_REFUSED);
    end;

    if GArgumentProblem <> '' then
    begin
      WriteLn(StdErr, GArgumentProblem);
      Exit(EXIT_REFUSED);
    end;

    if not GPreflight then
    begin
      WriteLn(StdErr, 'usage: wsm-install [-h] [--version] [--preflight] ' +
                      '--report PATH --backend {guix} [--dry-run]');
      WriteLn(StdErr, 'wsm-install: error: --preflight is required');
      Exit(EXIT_REFUSED);
    end;
    if not GDryRun then
    begin
      WriteLn(StdErr, 'usage: wsm-install [-h] [--version] [--preflight] ' +
                      '--report PATH --backend {guix} [--dry-run]');
      WriteLn(StdErr, 'wsm-install: error: --dry-run is required; this prototype ' +
                      'never performs deployment');
      Exit(EXIT_REFUSED);
    end;

    if not ReadReportFile(GReportPath, Source, LoadError) then
    begin
      WriteLn(StdErr, 'wsm-install: cannot read report: ' + LoadError);
      Exit(EXIT_REFUSED);
    end;

    Report := nil;
    try
      try
        Report := ParseJson(Source);
      except
        on E: EWsmJsonError do
        begin
          WriteLn(StdErr, 'wsm-install: invalid report JSON: ' + E.Message);
          Exit(EXIT_REFUSED);
        end;
      end;
      if (Report = nil) or (not Report.IsObject) then
      begin
        WriteLn(StdErr, 'wsm-install: invalid report JSON: top-level value must be an object');
        Exit(EXIT_REFUSED);
      end;

      { The report is validated against the schema for the version it
        declares, so a 1.0.0 report stays readable after 1.1.0 became current. }
      if not SelectVersion(Report, Version) then
        Exit(EXIT_REFUSED);

      CheckReport(Report, Version);
      if GErrorCount > 0 then
      begin
        for Index := 0 to GErrors.Count - 1 do
          WriteLn(StdErr, GErrors[Index]);
        if GErrorCount > MAX_SCHEMA_ERRORS then
          WriteLn(StdErr, Format('wsm-install: %d additional schema errors omitted',
            [GErrorCount - MAX_SCHEMA_ERRORS]));
        Exit(EXIT_REFUSED);
      end;

      if GClassify then
      begin
        Document := ClassifyReport(Report);
        try
          WriteLn(Document.Render(2));
        finally
          Document.Free;
        end;
        Exit(EXIT_OK);
      end;

      EvaluatePlanRules(Report);
      if not GQuiet then
      begin
        WriteLn(StdErr, SummarizeReport(Report));
        for Index := 0 to GWarnings.Count - 1 do
          WriteLn(StdErr, 'WARNING: ' + GWarnings[Index]);
        for Index := 0 to GBlockers.Count - 1 do
          WriteLn(StdErr, 'BLOCKED: ' + GBlockers[Index]);
      end;

      if GBlockers.Count > 0 then
      begin
        WriteLn(StdErr, 'wsm-install: no plan emitted because required critical ' +
                        'evidence is unresolved');
        Exit(EXIT_BLOCKED);
      end;

      { Accepted. The Python CLI writes the draft plan here; this front end
        does not build it. Saying so on stderr is the honest alternative to
        printing a document nobody validated. }
      WriteLn(StdErr, 'wsm-install: report accepted; the draft plan document is not ' +
                      'emitted by the Free Pascal front end (see docs/FPC-INSTALL-CLI.md)');
      Document := BuildPreflightResult(Report, Version);
      try
        WriteLn(Document.Render(2));
      finally
        Document.Free;
      end;
      Result := EXIT_OK;
    finally
      Report.Free;
    end;
  finally
    GErrors.Free;
    GWarnings.Free;
    GBlockers.Free;
  end;
end;

begin
  ExitCode := Run;
end.
