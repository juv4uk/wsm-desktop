unit wsmplan;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Plan-model slice of the FPC port.

  Reproduces the data and validation parts of wsm_install/plan.py and
  wsm_install/partition.py: the plan document, its canonical serialization and
  digest, the device-path rule, the two refusal ladders, the sgdisk argv lists
  and the review rendering.

  What is deliberately NOT here, and why:

  * the profile-evidence half of build_plan (wsm_install/profile.py). It stats
    directories, refuses symbolic links, reads artifact bytes and loads the
    evidence schema from disk. That branch belongs to the evidence slice; this
    unit takes the provenance it would have computed as a value
    (TProfileProvenance) and never touches a file.
  * plan_steps and backend_command (wsm_install/install_steps.py). Those are
    the steps slice; wsmsteps.pas already owns device_for and the argv rules.
  * anything that opens a block device. Neither ported module does: the size in
    TDisk arrives from the report or from --target-size-bytes, and cli.py
    labels it "user-supplied planning estimate; not read from the block
    device". Probing lives in wsm_hwcheck/collector.py, guided.py and tui.py.

  The canonical serializer is hand-written for the same reason plan_digest.pas
  hand-wrote one: fpjson iterates in insertion order and writes uppercase hex
  escapes, and either difference is a different digest. Every key is emitted in
  sorted order. The plan document contains no JSON numbers - only strings,
  booleans, null and arrays - so no number formatting is required; a number
  reaching this serializer would be a bug in the caller, not a formatting
  problem.

  Two Python details are reproduced on purpose, because callers already depend
  on them:

  * validate_target uses re.match and validate_confirmation uses re.fullmatch,
    so a path ending in a newline passes the first and fails the second. The
    port keeps that difference (DevicePathMatches versus DevicePathIsWhole)
    rather than quietly harmonizing it - see FPC-PLAN-SLICE.md.
  * Refused.__str__ is "<code>: <message>", which is what cli.py prints, so
    RefusalText reproduces that concatenation.

  Not compiled in the environment where this was written (no FPC there). The
  self-checks in wsmplan_vectors.pas are the acceptance test. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, wsm_sha256;

const
  { ---- wsm_install/plan.py ---- }
  PLAN_VERSION = '0.1.0';
  PLAN_MODE = 'dry-run';
  PLAN_STATUS = 'diagnostic-only';
  BACKEND_ID = 'guix-system';
  BACKEND_SUPPORTED = 'guix';
  BACKEND_UNSUPPORTED =
    'unsupported backend; the first WSM preview supports only ''guix''';

  { ---- wsm_install/partition.py ---- }
  ESP_MIB = 512;
  BIOS_BOOT_MIB = 1;
  MIN_ROOT_MIB = 12 * 1024;
  SIZE_TOLERANCE = 0.02;
  { (MIN_ROOT_MIB + ESP_MIB) * 1024 * 1024 - spelled out because FPC does not
    evaluate an Int64 cast inside a const expression. }
  MIN_LAYOUT_BYTES = 13421772800;

  { Refusal codes. A code is a contract: callers branch on it, so it is a
    constant here rather than a literal at each raise site. }
  CODE_DISK_PATH = 'disk.path';
  CODE_DISK_FIRMWARE = 'disk.firmware';
  CODE_DISK_RUNNING_SYSTEM = 'disk.running-system';
  CODE_DISK_TOO_SMALL = 'disk.too-small';
  CODE_DISK_ACKNOWLEDGEMENT = 'disk.acknowledgement';
  CODE_DISK_SIZE_DRIFT = 'disk.size-drift';
  CODE_DISK_SIZE_UNRECORDED = 'disk.size-unrecorded';

type
  TStringArray = array of string;
  TArgv = array of string;
  TArgvList = array of TArgv;

  { Refused, as a value instead of an exception. Code = '' means "no refusal",
    which is how every validation function here reports agreement. }
  TRefusal = record
    Code: string;
    Message: string;
  end;

  TPartition = record
    Number: Integer;
    StartText: string;      { '1MiB' }
    EndText: string;        { '513MiB', or '0' for "to the end of the disk" }
    TypeCode: string;
    Name: string;
    Role: string;
  end;
  TPartitions = array of TPartition;

  { What we believe about the target disk, taken from a report, not a probe. }
  TDisk = record
    Path: string;
    SizeBytes: Int64;
    IsRemovable: Boolean;
    HoldsRunningSystem: Boolean;
    HasExistingData: Boolean;
  end;

  TLayout = record
    Firmware: string;
    Disk: string;
    Partitions: TPartitions;
    Acknowledgement: string;
    { Python distinguishes None from '', and the refusal message prints them
      differently: "(got None)" versus "(got '')". }
    AcknowledgementGiven: Boolean;
    DiskSizeBytes: Int64;
    DiskSizeRecorded: Boolean;
  end;

  { ---- plan model ---- }
  TEnvironment = record
    Architecture: string;
    KernelRelease: string;
    BootMode: string;
    Virtualization: string;
  end;

  TFunctionalTest = record
    Capability: string;
    Status: string;
  end;
  TFunctionalTests = array of TFunctionalTest;

  TFirmware = record
    Requirement: string;
    RuntimeStatus: string;
  end;

  TDevice = record
    DeviceID: string;
    Category: string;
    Criticality: TStringArray;
    DiscoveryStatus: string;
    DriverStatus: string;
    Firmware: TFirmware;
    FunctionalTests: TFunctionalTests;
    EvidenceCount: Integer;
    { Used by SummarizeReport only; the plan document ignores them. }
    IdentityModel: string;
    IdentityManufacturer: string;
    FirstEvidenceSource: string;
    FirstEvidenceObservedAt: string;
    FirstEvidenceConfidence: string;
  end;
  TDevices = array of TDevice;

  TReport = record
    SchemaVersion: string;
    ReportID: string;
    CollectedAt: string;
    Environment: TEnvironment;
    Devices: TDevices;
    Warnings: TStringArray;
  end;

  { The result of the evidence slice's checks, as data. Present = False is the
    normal state: absence of verified evidence is not a failure. }
  TProfileProvenance = record
    Present: Boolean;
    Slug: string;
    ReportID: string;
    ReportSchemaVersion: string;
    Sha256: string;
  end;

  TPlan = record
    BodyJson: string;        { canonical document, before the digest field }
    PlanSha256: string;      { SHA-256 over BodyJson }
    CanonicalJson: string;   { the same document with plan_sha256 inserted }
    Blockers: TStringArray;
    Warnings: TStringArray;
  end;

{ Python repr() for the strings this slice prints: single quotes, backslash
  escapes, and the same treatment of control characters. }
function PyRepr(const S: string): string;
function PyReprOrNone(const S: string; Given: Boolean): string;

{ re.fullmatch over ^/dev/(sd[a-z]+|nvme[0-9]+n[0-9]+|vd[a-z]+|mmcblk[0-9]+)$ }
function DevicePathIsWhole(const Path: string): Boolean;
{ re.match over the same pattern - the trailing-newline difference is real. }
function DevicePathMatches(const Path: string): Boolean;

function RefusalText(const R: TRefusal): string;
function NoRefusal: TRefusal;

function ValidateTarget(const Disk: TDisk; const Firmware, Acknowledgement: string;
  AcknowledgementGiven: Boolean; out Refusal: TRefusal): Boolean;
function ValidateConfirmation(const Layout: TLayout; out Refusal: TRefusal): Boolean;
function PlanLayout(const Disk: TDisk; const Firmware, Acknowledgement: string;
  AcknowledgementGiven, HasExpectedSize: Boolean; ExpectedSizeBytes: Int64;
  out Layout: TLayout; out Refusal: TRefusal): Boolean;
function LayoutCommands(const Layout: TLayout; out Refusal: TRefusal): TArgvList;
function RenderLayout(const Layout: TLayout; out Refusal: TRefusal): string;

function CanonicalJsonOf(const Plan: TPlan): string;
function BuildPlan(const Report: TReport; const ReportSha256, Backend: string;
  const Provenance: TProfileProvenance; out Plan: TPlan;
  out BackendError: string): Boolean;
function SummarizeReport(const Report: TReport): string;

implementation

const
  CRITICAL_REQUIRED: array[0..2] of string =
    ('boot-path', 'primary-display', 'input');
  USER_SELECTION_REQUIRED: array[0..0] of string =
    ('storage-install-target');

function PyRepr(const S: string): string;
var
  I: Integer;
  C: Char;
begin
  Result := '''';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    case C of
      '\': Result := Result + '\\';
      '''': Result := Result + '\''';
      #10: Result := Result + '\n';
      #13: Result := Result + '\r';
      #9: Result := Result + '\t';
    else
      if C < ' ' then
        Result := Result + '\x' + LowerCase(IntToHex(Ord(C), 2))
      else
        Result := Result + C;
    end;
  end;
  Result := Result + '''';
end;

function PyReprOrNone(const S: string; Given: Boolean): string;
begin
  if Given then
    Result := PyRepr(S)
  else
    Result := 'None';
end;

{ sd[a-z]+ | vd[a-z]+ }
function LettersTail(const S: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  if Length(S) < 3 then Exit;
  for I := 3 to Length(S) do
    if (S[I] < 'a') or (S[I] > 'z') then Exit;
  Result := True;
end;

{ digits from position Start, at least one }
function DigitsFrom(const S: string; Start: Integer): Boolean;
var
  I: Integer;
begin
  Result := False;
  if Length(S) < Start then Exit;
  for I := Start to Length(S) do
    if (S[I] < '0') or (S[I] > '9') then Exit;
  Result := True;
end;

{ nvme[0-9]+n[0-9]+ }
function NvmeTail(const S: string): Boolean;
var
  I, N: Integer;
begin
  Result := False;
  if (Length(S) < 7) or (Copy(S, 1, 4) <> 'nvme') then Exit;
  I := 5;
  N := 0;
  while (I <= Length(S)) and (S[I] >= '0') and (S[I] <= '9') do
  begin
    Inc(I);
    Inc(N);
  end;
  if N = 0 then Exit;
  if (I > Length(S)) or (S[I] <> 'n') then Exit;
  Result := DigitsFrom(S, I + 1);
end;

function DeviceBodyOk(const Rest: string): Boolean;
begin
  Result := False;
  if Rest = '' then Exit;
  if Copy(Rest, 1, 2) = 'sd' then
    Result := LettersTail(Rest)
  else if Copy(Rest, 1, 2) = 'vd' then
    Result := LettersTail(Rest)
  else if Copy(Rest, 1, 6) = 'mmcblk' then
    Result := DigitsFrom(Rest, 7)
  else
    Result := NvmeTail(Rest);
end;

function DevicePathIsWhole(const Path: string): Boolean;
begin
  Result := (Copy(Path, 1, 5) = '/dev/') and DeviceBodyOk(Copy(Path, 6, Length(Path)));
end;

function DevicePathMatches(const Path: string): Boolean;
begin
  { Python's $ also matches immediately before a single trailing newline. }
  if DevicePathIsWhole(Path) then
    Exit(True);
  Result := (Length(Path) > 0) and (Path[Length(Path)] = #10) and
            DevicePathIsWhole(Copy(Path, 1, Length(Path) - 1));
end;

function RefusalText(const R: TRefusal): string;
begin
  if R.Code = '' then
    Result := ''
  else
    Result := R.Code + ': ' + R.Message;
end;

function NoRefusal: TRefusal;
begin
  Result.Code := '';
  Result.Message := '';
end;

function Fail(const Code, Message: string; out Refusal: TRefusal): Boolean;
begin
  Refusal.Code := Code;
  Refusal.Message := Message;
  Result := False;
end;

{ Python's ':.1%' format, for the drift message. }
function DriftPercent(Drift: Double): string;
begin
  Result := Format('%.1f', [Drift * 100.0]) + '%';
end;

function TooSmallMessage(const Path: string; SizeBytes: Int64): string;
begin
  Result := Path + ' is ' + IntToStr(SizeBytes) + ' bytes; the smallest ' +
            'supported layout needs ' + IntToStr(MIN_ROOT_MIB + ESP_MIB) + ' MiB';
end;

function ValidateTarget(const Disk: TDisk; const Firmware, Acknowledgement: string;
  AcknowledgementGiven: Boolean; out Refusal: TRefusal): Boolean;
begin
  Refusal := NoRefusal;
  { The order below is the order of the refusal ladder in partition.py: the
    most fundamental reason first, so a caller reporting one reason reports the
    right one. }
  if not DevicePathMatches(Disk.Path) then
    Exit(Fail(CODE_DISK_PATH,
      PyRepr(Disk.Path) + ' is not a whole block device; partitions and images are refused',
      Refusal));
  if (Firmware <> 'uefi') and (Firmware <> 'bios') then
    Exit(Fail(CODE_DISK_FIRMWARE,
      'firmware must be ''uefi'' or ''bios'', got ' + PyRepr(Firmware), Refusal));
  if Disk.HoldsRunningSystem then
    Exit(Fail(CODE_DISK_RUNNING_SYSTEM,
      Disk.Path + ' holds the system we are running from', Refusal));
  if Disk.SizeBytes < MIN_LAYOUT_BYTES then
    Exit(Fail(CODE_DISK_TOO_SMALL, TooSmallMessage(Disk.Path, Disk.SizeBytes), Refusal));
  { LayoutCommands always starts with sgdisk --zap-all, which replaces the
    table even when inventory found no filesystem. Absence of discovered data
    is not consent to erase the disk. }
  if (not AcknowledgementGiven) or (Acknowledgement <> Disk.Path) then
    Exit(Fail(CODE_DISK_ACKNOWLEDGEMENT,
      'refusing destructive partition-table replacement without an acknowledgement ' +
      'that names exactly ' + PyRepr(Disk.Path) + ' (got ' +
      PyReprOrNone(Acknowledgement, AcknowledgementGiven) + ')', Refusal));
  Result := True;
end;

function ValidateConfirmation(const Layout: TLayout; out Refusal: TRefusal): Boolean;
begin
  Refusal := NoRefusal;
  if not DevicePathIsWhole(Layout.Disk) then
    Exit(Fail(CODE_DISK_PATH,
      PyRepr(Layout.Disk) + ' is not a whole block device', Refusal));
  if (not Layout.AcknowledgementGiven) or
     (Layout.Acknowledgement <> Layout.Disk) then
    Exit(Fail(CODE_DISK_ACKNOWLEDGEMENT,
      'destructive partition-table replacement requires confirmation naming exactly ' +
      PyRepr(Layout.Disk), Refusal));
  if (not Layout.DiskSizeRecorded) or (Layout.DiskSizeBytes <= 0) then
    Exit(Fail(CODE_DISK_SIZE_UNRECORDED,
      'layout does not retain the observed target disk size', Refusal));
  if Layout.DiskSizeBytes < MIN_LAYOUT_BYTES then
    Exit(Fail(CODE_DISK_TOO_SMALL,
      TooSmallMessage(Layout.Disk, Layout.DiskSizeBytes), Refusal));
  Result := True;
end;

function PlanLayout(const Disk: TDisk; const Firmware, Acknowledgement: string;
  AcknowledgementGiven, HasExpectedSize: Boolean; ExpectedSizeBytes: Int64;
  out Layout: TLayout; out Refusal: TRefusal): Boolean;
var
  Drift: Double;
  Expected: Int64;
  Cursor: Integer;
  P: TPartition;
begin
  Layout := Default(TLayout);
  if not ValidateTarget(Disk, Firmware, Acknowledgement, AcknowledgementGiven, Refusal) then
    Exit(False);
  if HasExpectedSize then
  begin
    Expected := ExpectedSizeBytes;
    if Expected < 1 then Expected := 1;
    Drift := Abs(Disk.SizeBytes - ExpectedSizeBytes) / Expected;
    if Drift > SIZE_TOLERANCE then
      Exit(Fail(CODE_DISK_SIZE_DRIFT,
        Disk.Path + ' reports ' + IntToStr(Disk.SizeBytes) + ' bytes but ' +
        IntToStr(ExpectedSizeBytes) + ' was expected (' + DriftPercent(Drift) +
        ' drift); the disk may have been replaced', Refusal));
  end;

  Layout.Firmware := Firmware;
  Layout.Disk := Disk.Path;
  Layout.Acknowledgement := Acknowledgement;
  Layout.AcknowledgementGiven := AcknowledgementGiven;
  Layout.DiskSizeBytes := Disk.SizeBytes;
  Layout.DiskSizeRecorded := True;
  SetLength(Layout.Partitions, 0);

  Cursor := 1;
  P.Number := 1;
  P.StartText := IntToStr(Cursor) + 'MiB';
  if Firmware = 'bios' then
  begin
    { GRUB on GPT needs somewhere to put its core image; 1 MiB is not decoration. }
    P.EndText := IntToStr(Cursor + BIOS_BOOT_MIB) + 'MiB';
    P.TypeCode := 'ef02';
    P.Name := 'wsm-bios-boot';
    P.Role := 'bios-grub';
    Inc(Cursor, BIOS_BOOT_MIB);
  end
  else
  begin
    P.EndText := IntToStr(Cursor + ESP_MIB) + 'MiB';
    P.TypeCode := 'ef00';
    P.Name := 'wsm-esp';
    P.Role := 'esp';
    Inc(Cursor, ESP_MIB);
  end;
  SetLength(Layout.Partitions, 1);
  Layout.Partitions[0] := P;

  { No swap partition on purpose: the profile uses zram. }
  P.Number := 2;
  P.StartText := IntToStr(Cursor) + 'MiB';
  P.EndText := '0';
  P.TypeCode := '8300';
  P.Name := 'wsm-root';
  P.Role := 'root';
  SetLength(Layout.Partitions, 2);
  Layout.Partitions[1] := P;

  Refusal := NoRefusal;
  Result := True;
end;

function LayoutCommands(const Layout: TLayout; out Refusal: TRefusal): TArgvList;
var
  I: Integer;
  Step: TArgv;
  N: string;
begin
  Result := nil;
  if not ValidateConfirmation(Layout, Refusal) then Exit;
  Refusal := NoRefusal;
  SetLength(Result, Length(Layout.Partitions) + 1);
  SetLength(Result[0], 3);
  Result[0][0] := 'sgdisk';
  Result[0][1] := '--zap-all';
  Result[0][2] := Layout.Disk;
  for I := 0 to High(Layout.Partitions) do
  begin
    N := IntToStr(Layout.Partitions[I].Number);
    SetLength(Step, 5);
    Step[0] := 'sgdisk';
    Step[1] := '--new=' + N + ':' + Layout.Partitions[I].StartText + ':' +
               Layout.Partitions[I].EndText;
    Step[2] := '--typecode=' + N + ':' + Layout.Partitions[I].TypeCode;
    Step[3] := '--change-name=' + N + ':' + Layout.Partitions[I].Name;
    Step[4] := Layout.Disk;
    Result[I + 1] := Step;
  end;
end;

function RenderLayout(const Layout: TLayout; out Refusal: TRefusal): string;
var
  Commands: TArgvList;
  I, J: Integer;
  Line: string;
begin
  Commands := LayoutCommands(Layout, Refusal);
  if Refusal.Code <> '' then Exit('');
  Result := '# ' + Layout.Disk + ': ' + Layout.Firmware + ' layout' + #10 +
            '# NOT EXECUTED - review first';
  for I := 0 to High(Commands) do
  begin
    Line := '';
    for J := 0 to High(Commands[I]) do
    begin
      if J > 0 then Line := Line + ' ';
      Line := Line + Commands[I][J];
    end;
    Result := Result + #10 + Line;
  end;
  Result := Result + #10;
end;

{ ---- canonical JSON ---- }

{ Python's json.dumps(ensure_ascii=False) escapes exactly these. Everything
  above #31 - including UTF-8 continuation bytes - passes through raw, which is
  why this unit must be built with $H+ and no code page conversion. }
function JsonEscape(const S: string): string;
var
  I: Integer;
  C: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    case C of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #8:  Result := Result + '\b';
      #9:  Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
    else
      if C < ' ' then
        Result := Result + '\u' + LowerCase(IntToHex(Ord(C), 4))
      else
        Result := Result + C;
    end;
  end;
end;

function JStr(const S: string): string;
begin
  Result := '"' + JsonEscape(S) + '"';
end;

function JStrArray(const Values: TStringArray): string;
var
  I: Integer;
begin
  Result := '[';
  for I := 0 to High(Values) do
  begin
    if I > 0 then Result := Result + ',';
    Result := Result + JStr(Values[I]);
  end;
  Result := Result + ']';
end;

function JPointerArray(const Prefix: string; Count: Integer): string;
var
  I: Integer;
begin
  Result := '[';
  for I := 0 to Count - 1 do
  begin
    if I > 0 then Result := Result + ',';
    Result := Result + '{"json_pointer":' + JStr(Prefix + IntToStr(I)) + '}';
  end;
  Result := Result + ']';
end;

procedure SortStrings(var Values: TStringArray);
var
  I, J: Integer;
  Tmp: string;
begin
  for I := 1 to High(Values) do
  begin
    Tmp := Values[I];
    J := I - 1;
    while (J >= 0) and (Values[J] > Tmp) do
    begin
      Values[J + 1] := Values[J];
      Dec(J);
    end;
    Values[J + 1] := Tmp;
  end;
end;

function CloneStrings(const Values: TStringArray): TStringArray;
var
  I: Integer;
begin
  SetLength(Result, Length(Values));
  for I := 0 to High(Values) do
    Result[I] := Values[I];
end;

function InArray(const Values: TStringArray; const Value: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 0 to High(Values) do
    if Values[I] = Value then Exit(True);
end;

function ContainsRole(const Roles: TStringArray; const Role: string): Boolean;
begin
  Result := InArray(Roles, Role);
end;

{ True when the device claims any role that the installer treats as critical. }
function IsCritical(const Roles: TStringArray): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 0 to High(CRITICAL_REQUIRED) do
    if ContainsRole(Roles, CRITICAL_REQUIRED[I]) then Exit(True);
end;

procedure AddString(var Values: TStringArray; const Value: string);
begin
  SetLength(Values, Length(Values) + 1);
  Values[High(Values)] := Value;
end;

function DeviceSummaryJson(const Report: TReport): string;
var
  I, J: Integer;
  Device: TDevice;
  Tests: string;
  Criticality: TStringArray;
begin
  Result := '[';
  for I := 0 to High(Report.Devices) do
  begin
    Device := Report.Devices[I];
    Criticality := CloneStrings(Device.Criticality);
    SortStrings(Criticality);
    Tests := '[';
    for J := 0 to High(Device.FunctionalTests) do
    begin
      if J > 0 then Tests := Tests + ',';
      Tests := Tests + '{"capability":' + JStr(Device.FunctionalTests[J].Capability) +
               ',"status":' + JStr(Device.FunctionalTests[J].Status) + '}';
    end;
    Tests := Tests + ']';
    if I > 0 then Result := Result + ',';
    Result := Result +
      '{"category":' + JStr(Device.Category) +
      ',"criticality":' + JStrArray(Criticality) +
      ',"device_id":' + JStr(Device.DeviceID) +
      ',"discovery_status":' + JStr(Device.DiscoveryStatus) +
      ',"driver_status":' + JStr(Device.DriverStatus) +
      ',"evidence_refs":' +
        JPointerArray('/devices/' + IntToStr(I) + '/evidence/', Device.EvidenceCount) +
      ',"firmware_requirement":' + JStr(Device.Firmware.Requirement) +
      ',"firmware_runtime_status":' + JStr(Device.Firmware.RuntimeStatus) +
      ',"functional_test_refs":' +
        JPointerArray('/devices/' + IntToStr(I) + '/functional_tests/',
                      Length(Device.FunctionalTests)) +
      ',"functional_tests":' + Tests + '}';
  end;
  Result := Result + ']';
end;

{ Python sorts CRITICAL_REQUIRED before writing role_coverage and
  missing_required_roles, and the declared order above is NOT sorted - 'input'
  sorts before 'primary-display'. Sorting here rather than declaring the
  constant in sorted order keeps the constant readable and the output right. }
function SortedCriticalRequired: TStringArray;
var
  I: Integer;
begin
  SetLength(Result, Length(CRITICAL_REQUIRED));
  for I := 0 to High(CRITICAL_REQUIRED) do
    Result[I] := CRITICAL_REQUIRED[I];
  SortStrings(Result);
end;

function RoleCoverageJson(const Roles: TStringArray): string;
var
  I: Integer;
  State: string;
  Order: TStringArray;
begin
  Order := SortedCriticalRequired;
  Result := '{';
  for I := 0 to High(Order) do
  begin
    if I > 0 then Result := Result + ',';
    if InArray(Roles, Order[I]) then
      State := 'observed'
    else
      State := 'not-collected';
    Result := Result + JStr(Order[I]) + ':' + JStr(State);
  end;
  Result := Result + '}';
end;

function BuildPlan(const Report: TReport; const ReportSha256, Backend: string;
  const Provenance: TProfileProvenance; out Plan: TPlan;
  out BackendError: string): Boolean;
var
  I, J: Integer;
  Device: TDevice;
  Observed: TStringArray;
  Missing: TStringArray;
  RoleOrder: TStringArray;
  Head, Tail, Prov: string;
  NetworkTested: Boolean;
  Message: string;
begin
  Plan := Default(TPlan);
  BackendError := '';
  if Backend <> BACKEND_SUPPORTED then
  begin
    BackendError := BACKEND_UNSUPPORTED;
    Exit(False);
  end;

  Plan.Blockers := nil;
  Plan.Warnings := nil;

  if not Provenance.Present then
    AddString(Plan.Warnings,
      'no verified hardware profile evidence for this machine; ' +
      'the plan remains diagnostic-only');

  Observed := nil;
  for I := 0 to High(Report.Devices) do
  begin
    Device := Report.Devices[I];
    for J := 0 to High(Device.Criticality) do
      if not InArray(Observed, Device.Criticality[J]) then
        AddString(Observed, Device.Criticality[J]);

    if IsCritical(Device.Criticality) and
       ((Device.DiscoveryStatus = 'unknown') or
        (Device.DiscoveryStatus = 'not-detected')) then
      AddString(Plan.Blockers, Device.DeviceID +
        ': required critical device discovery is ' + Device.DiscoveryStatus);

    if (Device.Firmware.Requirement = 'required') and
       ((Device.Firmware.RuntimeStatus = 'missing') or
        (Device.Firmware.RuntimeStatus = 'load-error')) then
    begin
      Message := Device.DeviceID + ': required runtime firmware is ' +
                 Device.Firmware.RuntimeStatus;
      if IsCritical(Device.Criticality) then
        AddString(Plan.Blockers, Message)
      else
        AddString(Plan.Warnings, Message);
    end;

    if ContainsRole(Device.Criticality, 'network-installation') then
    begin
      NetworkTested := False;
      for J := 0 to High(Device.FunctionalTests) do
        if ((Device.FunctionalTests[J].Capability = 'network-link') or
            (Device.FunctionalTests[J].Capability = 'network-connectivity')) and
           (Device.FunctionalTests[J].Status = 'passed') then
          NetworkTested := True;
      if not NetworkTested then
        AddString(Plan.Warnings, Device.DeviceID +
          ': network installation path is not functionally tested; ' +
          'offline installation may be required');
    end;
  end;

  for I := 0 to High(Report.Warnings) do
    if not InArray(Plan.Warnings, Report.Warnings[I]) then
      AddString(Plan.Warnings, Report.Warnings[I]);

  Missing := nil;
  RoleOrder := SortedCriticalRequired;
  for I := 0 to High(RoleOrder) do
    if not InArray(Observed, RoleOrder[I]) then
      AddString(Missing, RoleOrder[I]);
  for I := 0 to High(Missing) do
    AddString(Plan.Warnings, 'required role ' + PyRepr(Missing[I]) +
      ' is not represented in the report; plan remains diagnostic-only');
  AddString(Plan.Warnings,
    'storage target is not selected by hardware discovery; explicit user ' +
    'selection and immediate identity revalidation are still required');

  if Provenance.Present then
    Prov := '{"report_id":' + JStr(Provenance.ReportID) +
            ',"report_schema_version":' + JStr(Provenance.ReportSchemaVersion) +
            ',"sha256":' + JStr(Provenance.Sha256) +
            ',"slug":' + JStr(Provenance.Slug) + '}'
  else
    Prov := 'null';

  Head :=
    '{"backend":{"id":' + JStr(BACKEND_ID) + '}' +
    ',"blockers":' + JStrArray(Plan.Blockers) +
    ',"device_summary":' + DeviceSummaryJson(Report) +
    ',"environment":{"architecture":' + JStr(Report.Environment.Architecture) +
      ',"boot_mode":' + JStr(Report.Environment.BootMode) +
      ',"kernel_release":' + JStr(Report.Environment.KernelRelease) +
      ',"virtualization":' + JStr(Report.Environment.Virtualization) + '}' +
    ',"execution":{"backend_invoked":false,"disk_access_performed":false,' +
      '"dry_run":true,"mutations_authorized":false,"plan_confirmable":false}' +
    ',"plan_mode":' + JStr(PLAN_MODE) +
    ',"plan_readiness":{"confirmable":false,"missing_required_roles":' +
      JStrArray(Missing) + ',"required_user_actions":' +
      JStrArray(USER_SELECTION_REQUIRED) +
      ',"role_coverage":' + RoleCoverageJson(Observed) + '}';

  Tail :=
    ',"plan_status":' + JStr(PLAN_STATUS) +
    ',"plan_version":' + JStr(PLAN_VERSION) +
    ',"profile_evidence":' + Prov +
    ',"source_report":{"report_id":' + JStr(Report.ReportID) +
      ',"schema_version":' + JStr(Report.SchemaVersion) +
      ',"sha256":' + JStr(ReportSha256) + '}' +
    ',"warnings":' + JStrArray(Plan.Warnings) + '}';

  Plan.BodyJson := Head + Tail;
  Plan.PlanSha256 := SHA256Hexa(RawByteString(Plan.BodyJson));
  Plan.CanonicalJson := Head + ',"plan_sha256":"' + Plan.PlanSha256 + '"' + Tail;
  Result := True;
end;

function CanonicalJsonOf(const Plan: TPlan): string;
begin
  Result := Plan.CanonicalJson;
end;

function SummarizeReport(const Report: TReport): string;
var
  I, J: Integer;
  Device: TDevice;
  Discovered, Unknown: Integer;
  Label_, Tests, Provenance, Line: string;
begin
  Discovered := 0;
  Unknown := 0;
  for I := 0 to High(Report.Devices) do
  begin
    if Report.Devices[I].DiscoveryStatus = 'discovered' then Inc(Discovered);
    if Report.Devices[I].DiscoveryStatus = 'unknown' then Inc(Unknown);
  end;

  Result := 'WSM hardware preflight ' + #$E2#$80#$94 + ' report ' + Report.ReportID + #10;
  Result := Result + 'Schema: ' + Report.SchemaVersion + ' | collected: ' +
            Report.CollectedAt + #10;
  Result := Result + 'Environment: ' + Report.Environment.Architecture +
            ' | kernel ' + Report.Environment.KernelRelease +
            ' | boot ' + Report.Environment.BootMode +
            ' | virtualization ' + Report.Environment.Virtualization + #10;
  Result := Result + 'Devices: ' + IntToStr(Length(Report.Devices)) + ' total, ' +
            IntToStr(Discovered) + ' discovered, ' + IntToStr(Unknown) + ' unknown';

  for I := 0 to High(Report.Devices) do
  begin
    Device := Report.Devices[I];
    Label_ := Device.IdentityModel;
    if Label_ = '' then Label_ := Device.IdentityManufacturer;
    if Label_ = '' then Label_ := Device.DeviceID;
    Tests := '';
    for J := 0 to High(Device.FunctionalTests) do
    begin
      if J > 0 then Tests := Tests + ', ';
      Tests := Tests + Device.FunctionalTests[J].Capability + '=' +
               Device.FunctionalTests[J].Status;
    end;
    if Tests = '' then Tests := 'none';
    if Device.EvidenceCount > 0 then
      Provenance := 'source=' + Device.FirstEvidenceSource + ' @ ' +
                    Device.FirstEvidenceObservedAt + ' (' +
                    Device.FirstEvidenceConfidence + ')'
    else
      Provenance := 'source=unknown';
    Line := '- ' + Device.Category + ': ' + Label_ +
            '; discovery=' + Device.DiscoveryStatus +
            '; driver=' + Device.DriverStatus +
            '; firmware=' + Device.Firmware.RuntimeStatus +
            '; tests=[' + Tests + ']; ' + Provenance;
    Result := Result + #10 + Line;
  end;

  if Length(Report.Warnings) > 0 then
  begin
    Line := 'Report warnings: ';
    for I := 0 to High(Report.Warnings) do
    begin
      if I > 0 then Line := Line + '; ';
      Line := Line + Report.Warnings[I];
    end;
    Result := Result + #10 + Line;
  end;
end;

end.
