program wsmplan_vectors;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Self-check for the wsmplan unit.

  Every expected value below was printed by the repository's Python - the real
  wsm_install/plan.py and wsm_install/partition.py - and copied here verbatim;
  nothing is hand-computed. Regenerate with the command recorded in
  FPC-PLAN-SLICE.md:

    python3 gen_vectors.py            # writes vectors.json
    python3 mk_pas.py                 # rewrites this file from it

  The program rebuilds each case through the Pascal unit, compares, and halts 1
  on any difference. Usage:

    ./wsmplan-vectors [repo-root]

  Without an argument the root is the parent of the directory holding the
  executable, which is where `make` builds it; the four hardware reports are
  read from <root>/tests/fixtures/hardware/. }

{$mode objfpc}{$H+}

{ wsm_sha256 is listed explicitly: FPC does not re-export the identifiers of a
  unit that wsmplan uses in its interface section. }
uses
  SysUtils, Classes, fpjson, jsonparser, wsm_sha256, wsmplan;

var
  Checks: Integer = 0;
  Failures: Integer = 0;

procedure Pass(const Name: string);
begin
  Inc(Checks);
end;

procedure Fail(const Name, Detail: string);
begin
  Inc(Checks);
  Inc(Failures);
  WriteLn('FAIL ', Name);
  if Detail <> '' then
    WriteLn('     ', Detail);
end;

procedure ExpectStr(const Name, Actual, Expected: string);
begin
  if Actual = Expected then
    Pass(Name)
  else
    Fail(Name, 'expected ' + Expected + ' | actual ' + Actual);
end;

procedure ExpectRefusal(const Name: string; const R: TRefusal;
  const Code, Message: string);
begin
  if (R.Code = Code) and (R.Message = Message) then
    Pass(Name)
  else
    Fail(Name, 'expected ' + Code + ': ' + Message + ' | actual ' + RefusalText(R));
end;

procedure ExpectBool(const Name: string; Actual, Expected: Boolean);
begin
  if Actual = Expected then
    Pass(Name)
  else if Expected then
    Fail(Name, 'expected True, got False')
  else
    Fail(Name, 'expected False, got True');
end;

function MakeDisk(const Path: string; SizeBytes: Int64;
  HoldsRunningSystem: Boolean = False): TDisk;
begin
  Result := Default(TDisk);
  Result.Path := Path;
  Result.SizeBytes := SizeBytes;
  Result.HoldsRunningSystem := HoldsRunningSystem;
  Result.HasExistingData := True;
end;

function PartitionsCompact(const P: TPartitions): string;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to High(P) do
  begin
    if I > 0 then Result := Result + ';';
    Result := Result + IntToStr(P[I].Number) + '|' + P[I].StartText + '|' +
              P[I].EndText + '|' + P[I].TypeCode + '|' + P[I].Name + '|' +
              P[I].Role;
  end;
end;

function CommandsCompact(const C: TArgvList): string;
var
  I, J: Integer;
begin
  Result := '';
  for I := 0 to High(C) do
  begin
    if I > 0 then Result := Result + ';';
    for J := 0 to High(C[I]) do
    begin
      if J > 0 then Result := Result + ' ';
      Result := Result + C[I][J];
    end;
  end;
end;

function ReadFileBytes(const Path: string): RawByteString;
var
  Stream: TFileStream;
begin
  Stream := TFileStream.Create(Path, fmOpenRead or fmShareDenyWrite);
  try
    SetLength(Result, Stream.Size);
    if Stream.Size > 0 then
      Stream.ReadBuffer(Result[1], Stream.Size);
  finally
    Stream.Free;
  end;
end;

function GetStr(O: TJSONObject; const Key: string): string;
var
  D: TJSONData;
begin
  Result := '';
  if O = nil then Exit;
  D := O.Find(Key);
  if (D <> nil) and (D.JSONType = jtString) then
    Result := D.AsString;
end;

function GetObj(O: TJSONObject; const Key: string): TJSONObject;
var
  D: TJSONData;
begin
  Result := nil;
  if O = nil then Exit;
  D := O.Find(Key);
  if (D <> nil) and (D.JSONType = jtObject) then
    Result := TJSONObject(D);
end;

function GetArr(O: TJSONObject; const Key: string): TJSONArray;
var
  D: TJSONData;
begin
  Result := nil;
  if O = nil then Exit;
  D := O.Find(Key);
  if (D <> nil) and (D.JSONType = jtArray) then
    Result := TJSONArray(D);
end;

{ Declared before its body because JsonToReport calls it. }
procedure Devices2Strings(Arr: TJSONArray; var Values: TStringArray); forward;

{ The mapping from the hardware report to the fields the plan model reads. A
  field the report does not carry stays empty, exactly as Python's .get()
  default would leave it. }
function JsonToReport(D: TJSONData): TReport;
var
  O, Env, Dev, Fw, Identity, Evidence: TJSONObject;
  Devices, Tests, EvidenceList: TJSONArray;
  I, J: Integer;
  Item: TJSONData;
begin
  Result := Default(TReport);
  if (D = nil) or (D.JSONType <> jtObject) then Exit;
  O := TJSONObject(D);
  Result.SchemaVersion := GetStr(O, 'schema_version');
  Result.ReportID := GetStr(O, 'report_id');
  Result.CollectedAt := GetStr(O, 'collected_at');

  Env := GetObj(O, 'environment');
  Result.Environment.Architecture := GetStr(Env, 'architecture');
  Result.Environment.KernelRelease := GetStr(Env, 'kernel_release');
  Result.Environment.BootMode := GetStr(Env, 'boot_mode');
  Result.Environment.Virtualization := GetStr(Env, 'virtualization');

  Devices := GetArr(O, 'devices');
  if Devices <> nil then
  begin
    SetLength(Result.Devices, Devices.Count);
    for I := 0 to Devices.Count - 1 do
    begin
      Item := Devices.Items[I];
      Dev := nil;
      if Item.JSONType = jtObject then Dev := TJSONObject(Item);
      Result.Devices[I] := Default(TDevice);
      Result.Devices[I].DeviceID := GetStr(Dev, 'device_id');
      Result.Devices[I].Category := GetStr(Dev, 'category');
      Result.Devices[I].DiscoveryStatus := GetStr(Dev, 'discovery_status');

      Devices2Strings(GetArr(Dev, 'criticality'), Result.Devices[I].Criticality);

      Result.Devices[I].DriverStatus := GetStr(GetObj(Dev, 'driver'), 'status');
      Fw := GetObj(Dev, 'firmware');
      Result.Devices[I].Firmware.Requirement := GetStr(Fw, 'requirement');
      Result.Devices[I].Firmware.RuntimeStatus := GetStr(Fw, 'runtime_status');

      Tests := GetArr(Dev, 'functional_tests');
      if Tests <> nil then
      begin
        SetLength(Result.Devices[I].FunctionalTests, Tests.Count);
        for J := 0 to Tests.Count - 1 do
          if Tests.Items[J].JSONType = jtObject then
          begin
            Result.Devices[I].FunctionalTests[J].Capability :=
              GetStr(TJSONObject(Tests.Items[J]), 'capability');
            Result.Devices[I].FunctionalTests[J].Status :=
              GetStr(TJSONObject(Tests.Items[J]), 'status');
          end;
      end;

      EvidenceList := GetArr(Dev, 'evidence');
      if EvidenceList <> nil then
      begin
        Result.Devices[I].EvidenceCount := EvidenceList.Count;
        if (EvidenceList.Count > 0) and (EvidenceList.Items[0].JSONType = jtObject) then
        begin
          Evidence := TJSONObject(EvidenceList.Items[0]);
          Result.Devices[I].FirstEvidenceSource := GetStr(Evidence, 'source');
          Result.Devices[I].FirstEvidenceObservedAt := GetStr(Evidence, 'observed_at');
          Result.Devices[I].FirstEvidenceConfidence := GetStr(Evidence, 'confidence');
        end;
      end;

      Identity := GetObj(Dev, 'identity');
      Result.Devices[I].IdentityModel := GetStr(Identity, 'model');
      Result.Devices[I].IdentityManufacturer := GetStr(Identity, 'manufacturer');
    end;
  end;

  Devices2Strings(GetArr(O, 'warnings'), Result.Warnings);
end;

procedure Devices2Strings(Arr: TJSONArray; var Values: TStringArray);
var
  I: Integer;
begin
  Values := nil;
  if Arr = nil then Exit;
  SetLength(Values, Arr.Count);
  for I := 0 to Arr.Count - 1 do
    if Arr.Items[I].JSONType = jtString then
      Values[I] := Arr.Items[I].AsString
    else
      Values[I] := '';
end;

{ Joined with #1, which no warning or blocker text can contain: ';' appears
  inside the messages themselves, so it would make two different lists compare
  equal. }
function JoinStrings(const Values: TStringArray): string;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to High(Values) do
  begin
    if I > 0 then Result := Result + #1;
    Result := Result + Values[I];
  end;
end;

function ParseJsonText(const Text: string): TJSONData;
var
  Parser: TJSONParser;
  Stream: TMemoryStream;
begin
  Stream := TMemoryStream.Create;
  try
    if Length(Text) > 0 then
      Stream.WriteBuffer(Text[1], Length(Text));
    Stream.Position := 0;
    Parser := TJSONParser.Create(Stream, True);
    try
      Result := Parser.Parse;
    finally
      Parser.Free;
    end;
  finally
    Stream.Free;
  end;
end;

function LoadReport(const Path: string; out Raw: RawByteString): TReport;
var
  Parser: TJSONParser;
  Stream: TMemoryStream;
  Data: TJSONData;
begin
  Raw := ReadFileBytes(Path);
  Stream := TMemoryStream.Create;
  try
    if Length(Raw) > 0 then
      Stream.WriteBuffer(Raw[1], Length(Raw));
    Stream.Position := 0;
    Parser := TJSONParser.Create(Stream, True);
    try
      Data := Parser.Parse;
      try
        Result := JsonToReport(Data);
      finally
        Data.Free;
      end;
    finally
      Parser.Free;
    end;
  finally
    Stream.Free;
  end;
end;

var
  Root: string;
  L: TLayout;
  R: TRefusal;
  Plan: TPlan;
  BackendError: string;
  Raw: RawByteString;
  Report: TReport;
  Cmds: TArgvList;
  Prov: TProfileProvenance;
  SynthText: string;

begin
  if ParamCount >= 1 then
    Root := ParamStr(1)
  else
    Root := ExtractFileDir(ExtractFileDir(ExpandFileName(ParamStr(0))));

  { P01: uefi on a 256 GiB NVMe disk }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'uefi', '/dev/nvme0n1', True, False, 0, L, R) then
  begin
    ExpectStr('P01 partitions', PartitionsCompact(L.Partitions), '1|1MiB|513MiB|ef00|wsm-esp|esp;2|513MiB|0|8300|wsm-root|root');
    Cmds := LayoutCommands(L, R);
    ExpectStr('P01 commands', CommandsCompact(Cmds), 'sgdisk --zap-all /dev/nvme0n1;sgdisk --new=1:1MiB:513MiB --typecode=1:ef00 --change-name=1:wsm-e' + 'sp /dev/nvme0n1;sgdisk --new=2:513MiB:0 --typecode=2:8300 --change-name=2:wsm-root /dev/nvme0n1');
    ExpectStr('P01 render', RenderLayout(L, R), '# /dev/nvme0n1: uefi layout' + #10 + '# NOT EXECUTED - review first' +
    #10 + 'sgdisk --zap-all /dev/nvme0n1' + #10 +
    'sgdisk --new=1:1MiB:513MiB --typecode=1:ef00 --change-name=1:wsm-esp /dev/nvme0n1' + #10 + 'sgdisk --new=2:513MiB:0 --typecode=2:8300 --change-name=2:wsm-root /dev/nvme0n1' +
    #10);
  end
  else
    Fail('P01', 'unexpected refusal ' + RefusalText(R));

  { P02: bios on a 64 GiB SATA disk, with the size revalidated }
  if PlanLayout(MakeDisk('/dev/sda', 68719476736), 'bios', '/dev/sda', True, False, 0, L, R) then
  begin
    ExpectStr('P02 partitions', PartitionsCompact(L.Partitions), '1|1MiB|2MiB|ef02|wsm-bios-boot|bios-grub;2|2MiB|0|8300|wsm-root|root');
    Cmds := LayoutCommands(L, R);
    ExpectStr('P02 commands', CommandsCompact(Cmds), 'sgdisk --zap-all /dev/sda;sgdisk --new=1:1MiB:2MiB --typecode=1:ef02 --change-name=1:wsm-bios-bo' + 'ot /dev/sda;sgdisk --new=2:2MiB:0 --typecode=2:8300 --change-name=2:wsm-root /dev/sda');
    ExpectStr('P02 render', RenderLayout(L, R), '# /dev/sda: bios layout' + #10 + '# NOT EXECUTED - review first' +
    #10 + 'sgdisk --zap-all /dev/sda' + #10 +
    'sgdisk --new=1:1MiB:2MiB --typecode=1:ef02 --change-name=1:wsm-bios-boot /dev/sda' + #10 + 'sgdisk --new=2:2MiB:0 --typecode=2:8300 --change-name=2:wsm-root /dev/sda' +
    #10);
  end
  else
    Fail('P02', 'unexpected refusal ' + RefusalText(R));

  { P03: an empty disk still needs the exact acknowledgement }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'uefi', '/dev/nvme0n1', True, False, 0, L, R) then
  begin
    ExpectStr('P03 partitions', PartitionsCompact(L.Partitions), '1|1MiB|513MiB|ef00|wsm-esp|esp;2|513MiB|0|8300|wsm-root|root');
  end
  else
    Fail('P03', 'unexpected refusal ' + RefusalText(R));

  { P04: exactly the minimum size is accepted }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 13421772800), 'uefi', '/dev/nvme0n1', True, False, 0, L, R) then
  begin
    ExpectStr('P04 partitions', PartitionsCompact(L.Partitions), '1|1MiB|513MiB|ef00|wsm-esp|esp;2|513MiB|0|8300|wsm-root|root');
  end
  else
    Fail('P04', 'unexpected refusal ' + RefusalText(R));

  { P05: drift of exactly 2.0% is accepted }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 109521666048), 'bios', '/dev/nvme0n1', True, False, 0, L, R) then
  begin
    ExpectStr('P05 partitions', PartitionsCompact(L.Partitions), '1|1MiB|2MiB|ef02|wsm-bios-boot|bios-grub;2|2MiB|0|8300|wsm-root|root');
  end
  else
    Fail('P05', 'unexpected refusal ' + RefusalText(R));

  { P28: a trailing newline passes plan() but is refused by commands() }
  L := Default(TLayout);
  if PlanLayout(MakeDisk('/dev/sda' + #10, 274877906944), 'uefi', '/dev/sda' + #10, True, False, 0, L, R) then
  begin
    ExpectStr('P28 partitions', PartitionsCompact(L.Partitions), '1|1MiB|513MiB|ef00|wsm-esp|esp;2|513MiB|0|8300|wsm-root|root');
    if ValidateConfirmation(L, R) then
      Fail('P28 validate_confirmation', 'expected a refusal from validate_confirmation')
    else
      ExpectRefusal('P28 validate_confirmation', R, 'disk.path', '''/dev/sda\n'' is not a whole block device');
  end
  else
    Fail('P28', 'unexpected refusal ' + RefusalText(R));

  { P30: uefi on an mmcblk device }
  if PlanLayout(MakeDisk('/dev/mmcblk0', 34359738368), 'uefi', '/dev/mmcblk0', True, False, 0, L, R) then
  begin
    ExpectStr('P30 partitions', PartitionsCompact(L.Partitions), '1|1MiB|513MiB|ef00|wsm-esp|esp;2|513MiB|0|8300|wsm-root|root');
  end
  else
    Fail('P30', 'unexpected refusal ' + RefusalText(R));

  { P31: bios on a virtio disk }
  if PlanLayout(MakeDisk('/dev/vdb', 17179869184), 'bios', '/dev/vdb', True, False, 0, L, R) then
  begin
    ExpectStr('P31 partitions', PartitionsCompact(L.Partitions), '1|1MiB|2MiB|ef02|wsm-bios-boot|bios-grub;2|2MiB|0|8300|wsm-root|root');
  end
  else
    Fail('P31', 'unexpected refusal ' + RefusalText(R));

  { P27: the device regex: match() accepts one trailing newline, fullmatch() does not }
  ExpectBool('P27 match ''/dev/sda''', DevicePathMatches('/dev/sda'), True);
  ExpectBool('P27 fullmatch ''/dev/sda''', DevicePathIsWhole('/dev/sda'), True);
  ExpectBool('P27 match ''/dev/sda\n''', DevicePathMatches('/dev/sda' + #10), True);
  ExpectBool('P27 fullmatch ''/dev/sda\n''', DevicePathIsWhole('/dev/sda' + #10), False);
  ExpectBool('P27 match ''/dev/sdaa''', DevicePathMatches('/dev/sdaa'), True);
  ExpectBool('P27 fullmatch ''/dev/sdaa''', DevicePathIsWhole('/dev/sdaa'), True);
  ExpectBool('P27 match ''/dev/vdb''', DevicePathMatches('/dev/vdb'), True);
  ExpectBool('P27 fullmatch ''/dev/vdb''', DevicePathIsWhole('/dev/vdb'), True);
  ExpectBool('P27 match ''/dev/nvme0n1''', DevicePathMatches('/dev/nvme0n1'), True);
  ExpectBool('P27 fullmatch ''/dev/nvme0n1''', DevicePathIsWhole('/dev/nvme0n1'), True);
  ExpectBool('P27 match ''/dev/nvme0n1p1''', DevicePathMatches('/dev/nvme0n1p1'), False);
  ExpectBool('P27 fullmatch ''/dev/nvme0n1p1''', DevicePathIsWhole('/dev/nvme0n1p1'), False);
  ExpectBool('P27 match ''/dev/mmcblk0''', DevicePathMatches('/dev/mmcblk0'), True);
  ExpectBool('P27 fullmatch ''/dev/mmcblk0''', DevicePathIsWhole('/dev/mmcblk0'), True);
  ExpectBool('P27 match ''/dev/mmcblk0p1''', DevicePathMatches('/dev/mmcblk0p1'), False);
  ExpectBool('P27 fullmatch ''/dev/mmcblk0p1''', DevicePathIsWhole('/dev/mmcblk0p1'), False);
  ExpectBool('P27 match ''/dev/sd''', DevicePathMatches('/dev/sd'), False);
  ExpectBool('P27 fullmatch ''/dev/sd''', DevicePathIsWhole('/dev/sd'), False);
  ExpectBool('P27 match ''/dev/sda1''', DevicePathMatches('/dev/sda1'), False);
  ExpectBool('P27 fullmatch ''/dev/sda1''', DevicePathIsWhole('/dev/sda1'), False);
  ExpectBool('P27 match ''/tmp/disk.img''', DevicePathMatches('/tmp/disk.img'), False);
  ExpectBool('P27 fullmatch ''/tmp/disk.img''', DevicePathIsWhole('/tmp/disk.img'), False);
  ExpectBool('P27 match ''sda''', DevicePathMatches('sda'), False);
  ExpectBool('P27 fullmatch ''sda''', DevicePathIsWhole('sda'), False);
  ExpectBool('P27 match ''/dev/''', DevicePathMatches('/dev/'), False);
  ExpectBool('P27 fullmatch ''/dev/''', DevicePathIsWhole('/dev/'), False);
  ExpectBool('P27 match ''/dev/sda ''', DevicePathMatches('/dev/sda '), False);
  ExpectBool('P27 fullmatch ''/dev/sda ''', DevicePathIsWhole('/dev/sda '), False);

  { P06: a partition node is not a whole disk }
  if PlanLayout(MakeDisk('/dev/nvme0n1p1', 274877906944), 'uefi', '/dev/nvme0n1p1', True, False, 0, L, R) then
    Fail('P06', 'no refusal')
  else
    ExpectRefusal('P06', R, 'disk.path', '''/dev/nvme0n1p1'' is not a whole block device; partitions and images are refused');

  { P07: a disk image is not a whole disk }
  if PlanLayout(MakeDisk('/tmp/disk.img', 274877906944), 'uefi', '/tmp/disk.img', True, False, 0, L, R) then
    Fail('P07', 'no refusal')
  else
    ExpectRefusal('P07', R, 'disk.path', '''/tmp/disk.img'' is not a whole block device; partitions and images are refused');

  { P08: firmware outside the two supported values }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'coreboot', '/dev/nvme0n1', True, False, 0, L, R) then
    Fail('P08', 'no refusal')
  else
    ExpectRefusal('P08', R, 'disk.firmware', 'firmware must be ''uefi'' or ''bios'', got ''coreboot''');

  { P09: the disk we are running from }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944, True), 'uefi', '/dev/nvme0n1', True, False, 0, L, R) then
    Fail('P09', 'no refusal')
  else
    ExpectRefusal('P09', R, 'disk.running-system', '/dev/nvme0n1 holds the system we are running from');

  { P10: 4 GiB is below the minimum }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 4294967296), 'uefi', '/dev/nvme0n1', True, False, 0, L, R) then
    Fail('P10', 'no refusal')
  else
    ExpectRefusal('P10', R, 'disk.too-small', '/dev/nvme0n1 is 4294967296 bytes; the smallest supported layout needs 12800 MiB');

  { P11: one byte below the minimum }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 13421772799), 'uefi', '/dev/nvme0n1', True, False, 0, L, R) then
    Fail('P11', 'no refusal')
  else
    ExpectRefusal('P11', R, 'disk.too-small', '/dev/nvme0n1 is 13421772799 bytes; the smallest supported layout needs 12800 MiB');

  { P12: the bios layout needs the same minimum }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 4294967296), 'bios', '/dev/nvme0n1', True, False, 0, L, R) then
    Fail('P12', 'no refusal')
  else
    ExpectRefusal('P12', R, 'disk.too-small', '/dev/nvme0n1 is 4294967296 bytes; the smallest supported layout needs 12800 MiB');

  { P13: no acknowledgement at all }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'uefi', '', False, False, 0, L, R) then
    Fail('P13', 'no refusal')
  else
    ExpectRefusal('P13', R, 'disk.acknowledgement', 'refusing destructive partition-table replacement without an acknowledgement that names exactly ''' + '/dev/nvme0n1'' (got None)');

  { P14: a boolean 'yes' is not an acknowledgement }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'uefi', 'yes', True, False, 0, L, R) then
    Fail('P14', 'no refusal')
  else
    ExpectRefusal('P14', R, 'disk.acknowledgement', 'refusing destructive partition-table replacement without an acknowledgement that names exactly ''' + '/dev/nvme0n1'' (got ''yes'')');

  { P15: an acknowledgement for another disk }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'uefi', '/dev/sda', True, False, 0, L, R) then
    Fail('P15', 'no refusal')
  else
    ExpectRefusal('P15', R, 'disk.acknowledgement', 'refusing destructive partition-table replacement without an acknowledgement that names exactly ''' + '/dev/nvme0n1'' (got ''/dev/sda'')');

  { P16: an empty disk with no acknowledgement }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'uefi', '', False, False, 0, L, R) then
    Fail('P16', 'no refusal')
  else
    ExpectRefusal('P16', R, 'disk.acknowledgement', 'refusing destructive partition-table replacement without an acknowledgement that names exactly ''' + '/dev/nvme0n1'' (got None)');

  { P17: 300% size drift }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'uefi', '/dev/nvme0n1', True, True, 68719476736, L, R) then
    Fail('P17', 'no refusal')
  else
    ExpectRefusal('P17', R, 'disk.size-drift', '/dev/nvme0n1 reports 274877906944 bytes but 68719476736 was expected (300.0% drift); the disk ma' + 'y have been replaced');

  { P18: 33.3% size drift }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 107374182400), 'uefi', '/dev/nvme0n1', True, True, 80530636800, L, R) then
    Fail('P18', 'no refusal')
  else
    ExpectRefusal('P18', R, 'disk.size-drift', '/dev/nvme0n1 reports 107374182400 bytes but 80530636800 was expected (33.3% drift); the disk may' + ' have been replaced');

  { P19: drift one byte past the 2% tolerance }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 109521666049), 'uefi', '/dev/nvme0n1', True, True, 107374182400, L, R) then
    Fail('P19', 'no refusal')
  else
    ExpectRefusal('P19', R, 'disk.size-drift', '/dev/nvme0n1 reports 109521666049 bytes but 107374182400 was expected (2.0% drift); the disk may' + ' have been replaced');

  { P20: ordering: too-small wins over a missing acknowledgement }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 4294967296), 'uefi', '', False, False, 0, L, R) then
    Fail('P20', 'no refusal')
  else
    ExpectRefusal('P20', R, 'disk.too-small', '/dev/nvme0n1 is 4294967296 bytes; the smallest supported layout needs 12800 MiB');

  { P21: ordering: firmware wins over a missing acknowledgement }
  if PlanLayout(MakeDisk('/dev/nvme0n1', 274877906944), 'coreboot', '', False, False, 0, L, R) then
    Fail('P21', 'no refusal')
  else
    ExpectRefusal('P21', R, 'disk.firmware', 'firmware must be ''uefi'' or ''bios'', got ''coreboot''');

  { P22: ordering: path wins over bad firmware }
  if PlanLayout(MakeDisk('/tmp/disk.img', 274877906944), 'coreboot', '', False, False, 0, L, R) then
    Fail('P22', 'no refusal')
  else
    ExpectRefusal('P22', R, 'disk.path', '''/tmp/disk.img'' is not a whole block device; partitions and images are refused');

  { P23: a Layout whose disk string lost its /dev prefix }
  L := Default(TLayout);
  L.Firmware := 'uefi';
  L.Disk := 'nvme0n1';
  L.Acknowledgement := 'nvme0n1';
  L.AcknowledgementGiven := True;
  L.DiskSizeBytes := 274877906944;
  L.DiskSizeRecorded := True;
  if ValidateConfirmation(L, R) then
    Fail('P23', 'no refusal')
  else
    ExpectRefusal('P23', R, 'disk.path', '''nvme0n1'' is not a whole block device');

  { P24: a Layout that lost its acknowledgement }
  L := Default(TLayout);
  L.Firmware := 'uefi';
  L.Disk := '/dev/nvme0n1';
  L.Acknowledgement := '';
  L.AcknowledgementGiven := False;
  L.DiskSizeBytes := 274877906944;
  L.DiskSizeRecorded := True;
  if ValidateConfirmation(L, R) then
    Fail('P24', 'no refusal')
  else
    ExpectRefusal('P24', R, 'disk.acknowledgement', 'destructive partition-table replacement requires confirmation naming exactly ''/dev/nvme0n1''');

  { P25: a Layout that lost the observed size }
  L := Default(TLayout);
  L.Firmware := 'uefi';
  L.Disk := '/dev/nvme0n1';
  L.Acknowledgement := '/dev/nvme0n1';
  L.AcknowledgementGiven := True;
  L.DiskSizeBytes := 0;
  L.DiskSizeRecorded := False;
  if ValidateConfirmation(L, R) then
    Fail('P25', 'no refusal')
  else
    ExpectRefusal('P25', R, 'disk.size-unrecorded', 'layout does not retain the observed target disk size');

  { P26: a Layout below the minimum size }
  L := Default(TLayout);
  L.Firmware := 'uefi';
  L.Disk := '/dev/nvme0n1';
  L.Acknowledgement := '/dev/nvme0n1';
  L.AcknowledgementGiven := True;
  L.DiskSizeBytes := 1;
  L.DiskSizeRecorded := True;
  if ValidateConfirmation(L, R) then
    Fail('P26', 'no refusal')
  else
    ExpectRefusal('P26', R, 'disk.too-small', '/dev/nvme0n1 is 1 bytes; the smallest supported layout needs 12800 MiB');

  { P29: the same layout, at commands(): fullmatch refuses it }
  if PlanLayout(MakeDisk('/dev/sda' + #10, 274877906944), 'uefi', '/dev/sda' + #10, True, False, 0, L, R) then
  begin
    Cmds := LayoutCommands(L, R);
    ExpectRefusal('P29', R, 'disk.path', '''/dev/sda\n'' is not a whole block device');
  end
  else
    Fail('P29', 'plan refused before commands()')

  { ---- plan model vectors ---- }
  SynthText := '{' + #10 + '  "report_id": "synthetic-critical-firmware",' +
    #10 + '  "schema_version": "1.0.0",' + #10 +
    '  "collected_at": "2026-11-28T00:00:00Z",' + #10 + '  "environment": {' +
    #10 + '    "architecture": "x86_64",' + #10 +
    '    "kernel_release": "6.12.0-synthetic",' + #10 + '    "boot_mode": "uefi",' +
    #10 + '    "virtualization": "none-detected"' + #10 +
    '  },' + #10 + '  "devices": [' +
    #10 + '    {' + #10 +
    '      "device_id": "gpu-0001",' + #10 + '      "category": "gpu",' +
    #10 + '      "criticality": [' + #10 +
    '        "primary-display"' + #10 + '      ],' +
    #10 + '      "discovery_status": "discovered",' + #10 +
    '      "driver": {' + #10 + '        "status": "bound"' +
    #10 + '      },' + #10 +
    '      "firmware": {' + #10 + '        "requirement": "required",' +
    #10 + '        "runtime_status": "missing"' + #10 +
    '      },' + #10 + '      "functional_tests": [],' +
    #10 + '      "evidence": []' + #10 +
    '    },' + #10 + '    {' +
    #10 + '      "device_id": "net-0002",' + #10 +
    '      "category": "network",' + #10 + '      "criticality": [' +
    #10 + '        "network-installation"' + #10 +
    '      ],' + #10 + '      "discovery_status": "discovered",' +
    #10 + '      "driver": {' + #10 +
    '        "status": "bound"' + #10 + '      },' +
    #10 + '      "firmware": {' + #10 +
    '        "requirement": "required",' + #10 + '        "runtime_status": "missing"' +
    #10 + '      },' + #10 +
    '      "functional_tests": [' + #10 + '        {' +
    #10 + '          "capability": "network-link",' + #10 +
    '          "status": "passed"' + #10 + '        }' +
    #10 + '      ],' + #10 +
    '      "evidence": [' + #10 + '        {' +
    #10 + '          "source": "synthetic",' + #10 +
    '          "observed_at": "2026-11-28T00:00:00Z",' + #10 + '          "confidence": "high"' +
    #10 + '        }' + #10 +
    '      ]' + #10 + '    },' +
    #10 + '    {' + #10 +
    '      "device_id": "ssd-0001",' + #10 + '      "category": "storage-device",' +
    #10 + '      "criticality": [' + #10 +
    '        "boot-path"' + #10 + '      ],' +
    #10 + '      "discovery_status": "discovered",' + #10 +
    '      "driver": {' + #10 + '        "status": "bound"' +
    #10 + '      },' + #10 +
    '      "firmware": {' + #10 + '        "requirement": "not-required",' +
    #10 + '        "runtime_status": "not-needed"' + #10 +
    '      },' + #10 + '      "functional_tests": [],' +
    #10 + '      "evidence": [' + #10 +
    '        {' + #10 + '          "source": "synthetic-a",' +
    #10 + '          "observed_at": "2026-11-28T00:00:00Z",' + #10 +
    '          "confidence": "medium"' + #10 + '        },' +
    #10 + '        {' + #10 +
    '          "source": "synthetic-b",' + #10 + '          "observed_at": "2026-11-28T00:00:01Z",' +
    #10 + '          "confidence": "low"' + #10 +
    '        }' + #10 + '      ]' +
    #10 + '    },' + #10 +
    '    {' + #10 + '      "device_id": "kbd-0001",' +
    #10 + '      "category": "input",' + #10 +
    '      "criticality": [' + #10 + '        "input"' +
    #10 + '      ],' + #10 +
    '      "discovery_status": "discovered",' + #10 + '      "driver": {' +
    #10 + '        "status": "bound"' + #10 +
    '      },' + #10 + '      "firmware": {' +
    #10 + '        "requirement": "not-required",' + #10 +
    '        "runtime_status": "not-needed"' + #10 + '      },' +
    #10 + '      "functional_tests": [' + #10 +
    '        {' + #10 + '          "capability": "input-event",' +
    #10 + '          "status": "passed"' + #10 +
    '        }' + #10 + '      ],' +
    #10 + '      "evidence": []' + #10 +
    '    }' + #10 + '  ],' +
    #10 + '  "warnings": [' + #10 +
    '    "no verified hardware profile evidence for this machine; the plan remains diagnostic-only",' + #10 + '    "a report note that survives unchanged"' +
    #10 + '  ]' + #10 +
    '}';

  { J01: every device discovered, no criticality claimed (complete-machine.json) }
  Report := LoadReport(Root + '/tests/fixtures/hardware/complete-machine.json', Raw);
  Prov := Default(TProfileProvenance);
  if not BuildPlan(Report, SHA256Hexa(Raw), 'guix', Prov, Plan, BackendError) then
    Fail('J01', 'unexpected backend error: ' + BackendError)
  else
  begin
    ExpectStr('J01 canonical', Plan.CanonicalJson, '{"backend":{"id":"guix-system"},"blockers":[],"device_summary":[{"category":"cpu","criticality":' + '[],"device_id":"cpu-0","discovery_status":"discovered","driver_status":"bound","evidence_refs":[' + '{"json_pointer":"/devices/0/evidence/0"}],"firmware_requirement":"not-required","firmware_runtim' +
    'e_status":"not-needed","functional_test_refs":[],"functional_tests":[]},{"category":"motherboard' + '","criticality":[],"device_id":"mb-0","discovery_status":"discovered","driver_status":"bound","e' + 'vidence_refs":[{"json_pointer":"/devices/1/evidence/0"}],"firmware_requirement":"not-required","' +
    'firmware_runtime_status":"not-needed","functional_test_refs":[],"functional_tests":[]},{"categor' + 'y":"memory","criticality":[],"device_id":"mem-0","discovery_status":"discovered","driver_status"' + ':"bound","evidence_refs":[{"json_pointer":"/devices/2/evidence/0"}],"firmware_requirement":"not-' +
    'required","firmware_runtime_status":"not-needed","functional_test_refs":[],"functional_tests":[]' + '},{"category":"storage-device","criticality":[],"device_id":"nvme-0","discovery_status":"discove' + 'red","driver_status":"bound","evidence_refs":[{"json_pointer":"/devices/3/evidence/0"}],"firmwar' +
    'e_requirement":"not-required","firmware_runtime_status":"not-needed","functional_test_refs":[],"' + 'functional_tests":[]},{"category":"storage-controller","criticality":[],"device_id":"sata-0","di' + 'scovery_status":"discovered","driver_status":"bound","evidence_refs":[{"json_pointer":"/devices/' +
    '4/evidence/0"}],"firmware_requirement":"not-required","firmware_runtime_status":"not-needed","fu' + 'nctional_test_refs":[],"functional_tests":[]},{"category":"network","criticality":[],"device_id"' + ':"nic-0","discovery_status":"discovered","driver_status":"bound","evidence_refs":[{"json_pointer' +
    '":"/devices/5/evidence/0"}],"firmware_requirement":"not-required","firmware_runtime_status":"not' + '-needed","functional_test_refs":[],"functional_tests":[]},{"category":"gpu","criticality":[],"de' + 'vice_id":"gpu-0","discovery_status":"discovered","driver_status":"bound","evidence_refs":[{"json' +
    '_pointer":"/devices/6/evidence/0"}],"firmware_requirement":"not-required","firmware_runtime_stat' + 'us":"not-needed","functional_test_refs":[],"functional_tests":[]},{"category":"display","critica' + 'lity":[],"device_id":"disp-0","discovery_status":"discovered","driver_status":"bound","evidence_' +
    'refs":[{"json_pointer":"/devices/7/evidence/0"}],"firmware_requirement":"not-required","firmware' + '_runtime_status":"not-needed","functional_test_refs":[],"functional_tests":[]},{"category":"audi' + 'o","criticality":[],"device_id":"audio-0","discovery_status":"discovered","driver_status":"bound' +
    '","evidence_refs":[{"json_pointer":"/devices/8/evidence/0"}],"firmware_requirement":"not-require' + 'd","firmware_runtime_status":"not-needed","functional_test_refs":[],"functional_tests":[]},{"cat' + 'egory":"bluetooth","criticality":[],"device_id":"bt-0","discovery_status":"discovered","driver_s' +
    'tatus":"bound","evidence_refs":[{"json_pointer":"/devices/9/evidence/0"}],"firmware_requirement"' + ':"not-required","firmware_runtime_status":"not-needed","functional_test_refs":[],"functional_tes' + 'ts":[]},{"category":"input","criticality":[],"device_id":"kbd-0","discovery_status":"discovered"' +
    ',"driver_status":"bound","evidence_refs":[{"json_pointer":"/devices/10/evidence/0"}],"firmware_r' + 'equirement":"not-required","firmware_runtime_status":"not-needed","functional_test_refs":[],"fun' + 'ctional_tests":[]},{"category":"usb-controller","criticality":[],"device_id":"usb-0","discovery_' +
    'status":"discovered","driver_status":"bound","evidence_refs":[{"json_pointer":"/devices/11/evide' + 'nce/0"}],"firmware_requirement":"not-required","firmware_runtime_status":"not-needed","functiona' + 'l_test_refs":[],"functional_tests":[]},{"category":"camera","criticality":[],"device_id":"cam-0"' +
    ',"discovery_status":"discovered","driver_status":"bound","evidence_refs":[{"json_pointer":"/devi' + 'ces/12/evidence/0"}],"firmware_requirement":"not-required","firmware_runtime_status":"not-needed' + '","functional_test_refs":[],"functional_tests":[]},{"category":"other","criticality":[],"device_' +
    'id":"other-0","discovery_status":"discovered","driver_status":"bound","evidence_refs":[{"json_po' + 'inter":"/devices/13/evidence/0"}],"firmware_requirement":"not-required","firmware_runtime_status' + '":"not-needed","functional_test_refs":[],"functional_tests":[]}],"environment":{"architecture":"' +
    'x86_64","boot_mode":"uefi","kernel_release":"6.12.0-example","virtualization":"none-detected"},"' + 'execution":{"backend_invoked":false,"disk_access_performed":false,"dry_run":true,"mutations_auth' + 'orized":false,"plan_confirmable":false},"plan_mode":"dry-run","plan_readiness":{"confirmable":fa' +
    'lse,"missing_required_roles":["boot-path","input","primary-display"],"required_user_actions":["s' + 'torage-install-target"],"role_coverage":{"boot-path":"not-collected","input":"not-collected","pr' + 'imary-display":"not-collected"}},"plan_sha256":"bbeb46832d9f36059207aabb5bdb42b093441bd8f326a699' +
    'ae0629bff6122689","plan_status":"diagnostic-only","plan_version":"0.1.0","profile_evidence":null' + ',"source_report":{"report_id":"fixture-complete-machine-20261126","schema_version":"1.0.0","sha2' + '56":"99715d522ea09753bcdedecaf1ccdab89edc285a0f474410130debb0ccd6f166"},"warnings":["no verified' +
    ' hardware profile evidence for this machine; the plan remains diagnostic-only","required role ''b' + 'oot-path'' is not represented in the report; plan remains diagnostic-only","required role ''input''' + ' is not represented in the report; plan remains diagnostic-only","required role ''primary-display' +
    ''' is not represented in the report; plan remains diagnostic-only","storage target is not selecte' + 'd by hardware discovery; explicit user selection and immediate identity revalidation are still r' + 'equired"]}');
    ExpectStr('J01 plan_sha256', Plan.PlanSha256, 'bbeb46832d9f36059207aabb5bdb42b093441bd8f326a699ae0629bff6122689');
    ExpectStr('J01 blockers', JoinStrings(Plan.Blockers), '');
    ExpectStr('J01 warnings', JoinStrings(Plan.Warnings), 'no verified hardware profile evidence for this machine; the plan remains diagnostic-only' + #1 + 'required role ''boot-path'' is not represented in the report; plan remains diagnostic-only' +
    #1 + 'required role ''input'' is not represented in the report; plan remains diagnostic-only' + #1 +
    'required role ''primary-display'' is not represented in the report; plan remains diagnostic-only' + #1 + 'storage target is not selected by hardware discovery; explicit user selection and immediate iden' +
    'tity revalidation are still required');
    ExpectStr('J01 summary', SummarizeReport(Report), 'WSM hardware preflight — report fixture-complete-machine-20261126' + #10 + 'Schema: 1.0.0 | collected: 2026-11-25T13:45:00Z' +
    #10 + 'Environment: x86_64 | kernel 6.12.0-example | boot uefi | virtualization none-detected' + #10 +
    'Devices: 14 total, 14 discovered, 0 unknown' + #10 + '- cpu: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; source=pr' +
    'ocfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- motherboard: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; s' +
    'ource=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- memory: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; source' +
    '=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- storage-device: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]' +
    '; source=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- storage-controller: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[n' +
    'one]; source=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- network: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; sourc' +
    'e=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- gpu: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; source=pr' +
    'ocfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- display: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; sourc' +
    'e=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- audio: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; source=' +
    'procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- bluetooth: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; sou' +
    'rce=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- input: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; source=' +
    'procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- usb-controller: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]' +
    '; source=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- camera: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; source' +
    '=procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)' + #10 + '- other: Fixture; discovery=discovered; driver=bound; firmware=not-needed; tests=[none]; source=' +
    'procfs:/cpuinfo @ 2026-11-26T00:00:00Z (confirmed)');
  end

  { J02: one observed primary display (desktop-observed.json) }
  Report := LoadReport(Root + '/tests/fixtures/hardware/desktop-observed.json', Raw);
  Prov := Default(TProfileProvenance);
  if not BuildPlan(Report, SHA256Hexa(Raw), 'guix', Prov, Plan, BackendError) then
    Fail('J02', 'unexpected backend error: ' + BackendError)
  else
  begin
    ExpectStr('J02 canonical', Plan.CanonicalJson, '{"backend":{"id":"guix-system"},"blockers":[],"device_summary":[{"category":"gpu","criticality":' + '["primary-display"],"device_id":"dev-0001","discovery_status":"discovered","driver_status":"boun' + 'd","evidence_refs":[{"json_pointer":"/devices/0/evidence/0"}],"firmware_requirement":"unknown","' +
    'firmware_runtime_status":"unknown","functional_test_refs":[],"functional_tests":[]},{"category":' + '"display","criticality":["primary-display"],"device_id":"dev-0002","discovery_status":"discovere' + 'd","driver_status":"not-applicable","evidence_refs":[{"json_pointer":"/devices/1/evidence/0"}],"' +
    'firmware_requirement":"not-required","firmware_runtime_status":"not-needed","functional_test_ref' + 's":[],"functional_tests":[]}],"environment":{"architecture":"x86_64","boot_mode":"uefi","kernel_' + 'release":"6.12.0-example","virtualization":"none-detected"},"execution":{"backend_invoked":false' +
    ',"disk_access_performed":false,"dry_run":true,"mutations_authorized":false,"plan_confirmable":fa' + 'lse},"plan_mode":"dry-run","plan_readiness":{"confirmable":false,"missing_required_roles":["boot' + '-path","input"],"required_user_actions":["storage-install-target"],"role_coverage":{"boot-path":' +
    '"not-collected","input":"not-collected","primary-display":"observed"}},"plan_sha256":"77962029bc' + 'cc11f6c4452edf949e9a9f6a4c0a4080ed00e6542a7779f9e342f0","plan_status":"diagnostic-only","plan_ve' + 'rsion":"0.1.0","profile_evidence":null,"source_report":{"report_id":"example-desktop-20261125-a1' +
    '","schema_version":"1.0.0","sha256":"cf7d17d42c66afe674224553b969d94bf9ef57bfe3ce779805e73b694b7' + '87b33"},"warnings":["no verified hardware profile evidence for this machine; the plan remains di' + 'agnostic-only","required role ''boot-path'' is not represented in the report; plan remains diagnos' +
    'tic-only","required role ''input'' is not represented in the report; plan remains diagnostic-only"' + ',"storage target is not selected by hardware discovery; explicit user selection and immediate id' + 'entity revalidation are still required"]}');
    ExpectStr('J02 plan_sha256', Plan.PlanSha256, '77962029bccc11f6c4452edf949e9a9f6a4c0a4080ed00e6542a7779f9e342f0');
    ExpectStr('J02 blockers', JoinStrings(Plan.Blockers), '');
    ExpectStr('J02 warnings', JoinStrings(Plan.Warnings), 'no verified hardware profile evidence for this machine; the plan remains diagnostic-only' + #1 + 'required role ''boot-path'' is not represented in the report; plan remains diagnostic-only' +
    #1 + 'required role ''input'' is not represented in the report; plan remains diagnostic-only' + #1 +
    'storage target is not selected by hardware discovery; explicit user selection and immediate iden' + 'tity revalidation are still required');
    ExpectStr('J02 summary', SummarizeReport(Report), 'WSM hardware preflight — report example-desktop-20261125-a1' + #10 + 'Schema: 1.0.0 | collected: 2026-11-25T13:45:00Z' +
    #10 + 'Environment: x86_64 | kernel 6.12.0-example | boot uefi | virtualization none-detected' + #10 +
    'Devices: 2 total, 2 discovered, 0 unknown' + #10 + '- gpu: Example GPU; discovery=discovered; driver=bound; firmware=unknown; tests=[none]; source=s' +
    'ysfs:/sys/bus/pci/devices @ 2026-11-25T13:45:00Z (confirmed)' + #10 + '- display: dev-0002; discovery=discovered; driver=not-applicable; firmware=not-needed; tests=[no' +
    'ne]; source=sysfs:/sys/class/drm @ 2026-11-25T13:45:00Z (confirmed)');
  end

  { J03: required network firmware failed to load (missing-firmware.json) }
  Report := LoadReport(Root + '/tests/fixtures/hardware/missing-firmware.json', Raw);
  Prov := Default(TProfileProvenance);
  if not BuildPlan(Report, SHA256Hexa(Raw), 'guix', Prov, Plan, BackendError) then
    Fail('J03', 'unexpected backend error: ' + BackendError)
  else
  begin
    ExpectStr('J03 canonical', Plan.CanonicalJson, '{"backend":{"id":"guix-system"},"blockers":[],"device_summary":[{"category":"network","criticali' + 'ty":["network-installation"],"device_id":"net-0001","discovery_status":"discovered","driver_stat' + 'us":"bound","evidence_refs":[{"json_pointer":"/devices/0/evidence/0"}],"firmware_requirement":"r' +
    'equired","firmware_runtime_status":"load-error","functional_test_refs":[{"json_pointer":"/device' + 's/0/functional_tests/0"}],"functional_tests":[{"capability":"network-link","status":"not-run"}]}' + '],"environment":{"architecture":"x86_64","boot_mode":"uefi","kernel_release":"6.12.0-example","v' +
    'irtualization":"none-detected"},"execution":{"backend_invoked":false,"disk_access_performed":fal' + 'se,"dry_run":true,"mutations_authorized":false,"plan_confirmable":false},"plan_mode":"dry-run","' + 'plan_readiness":{"confirmable":false,"missing_required_roles":["boot-path","input","primary-disp' +
    'lay"],"required_user_actions":["storage-install-target"],"role_coverage":{"boot-path":"not-colle' + 'cted","input":"not-collected","primary-display":"not-collected"}},"plan_sha256":"e30add98d37a501' + 'b41ac10f3c52e233d633bbb7d81b3a61a355a4cab84c9c5e8","plan_status":"diagnostic-only","plan_version' +
    '":"0.1.0","profile_evidence":null,"source_report":{"report_id":"example-firmware-20261125-b2","s' + 'chema_version":"1.0.0","sha256":"6ce178ea58b517a1ca0af1e253027325cf580564664aa7263c10f955498e48e' + '8"},"warnings":["no verified hardware profile evidence for this machine; the plan remains diagno' +
    'stic-only","net-0001: required runtime firmware is load-error","net-0001: network installation p' + 'ath is not functionally tested; offline installation may be required","Network installation may ' + 'be unavailable until firmware is provided.","required role ''boot-path'' is not represented in the' +
    ' report; plan remains diagnostic-only","required role ''input'' is not represented in the report; ' + 'plan remains diagnostic-only","required role ''primary-display'' is not represented in the report;' + ' plan remains diagnostic-only","storage target is not selected by hardware discovery; explicit u' +
    'ser selection and immediate identity revalidation are still required"]}');
    ExpectStr('J03 plan_sha256', Plan.PlanSha256, 'e30add98d37a501b41ac10f3c52e233d633bbb7d81b3a61a355a4cab84c9c5e8');
    ExpectStr('J03 blockers', JoinStrings(Plan.Blockers), '');
    ExpectStr('J03 warnings', JoinStrings(Plan.Warnings), 'no verified hardware profile evidence for this machine; the plan remains diagnostic-only' + #1 + 'net-0001: required runtime firmware is load-error' +
    #1 + 'net-0001: network installation path is not functionally tested; offline installation may be requ' + 'ired' +
    #1 + 'Network installation may be unavailable until firmware is provided.' + #1 +
    'required role ''boot-path'' is not represented in the report; plan remains diagnostic-only' + #1 + 'required role ''input'' is not represented in the report; plan remains diagnostic-only' +
    #1 + 'required role ''primary-display'' is not represented in the report; plan remains diagnostic-only' + #1 +
    'storage target is not selected by hardware discovery; explicit user selection and immediate iden' + 'tity revalidation are still required');
    ExpectStr('J03 summary', SummarizeReport(Report), 'WSM hardware preflight — report example-firmware-20261125-b2' + #10 + 'Schema: 1.0.0 | collected: 2026-11-25T13:46:00Z' +
    #10 + 'Environment: x86_64 | kernel 6.12.0-example | boot uefi | virtualization none-detected' + #10 +
    'Devices: 1 total, 1 discovered, 0 unknown' + #10 + '- network: net-0001; discovery=discovered; driver=bound; firmware=load-error; tests=[network-lin' +
    'k=not-run]; source=kernel ring buffer @ 2026-11-25T13:46:00Z (confirmed)' + #10 + 'Report warnings: Network installation may be unavailable until firmware is provided.');
  end

  { J04: a critical role is unknown, so the plan is blocked (unknown-incomplete.json) }
  Report := LoadReport(Root + '/tests/fixtures/hardware/unknown-incomplete.json', Raw);
  Prov := Default(TProfileProvenance);
  if not BuildPlan(Report, SHA256Hexa(Raw), 'guix', Prov, Plan, BackendError) then
    Fail('J04', 'unexpected backend error: ' + BackendError)
  else
  begin
    ExpectStr('J04 canonical', Plan.CanonicalJson, '{"backend":{"id":"guix-system"},"blockers":["display-0001: required critical device discovery is' + ' unknown"],"device_summary":[{"category":"display","criticality":["primary-display"],"device_id"' + ':"display-0001","discovery_status":"unknown","driver_status":"unknown","evidence_refs":[],"firmw' +
    'are_requirement":"unknown","firmware_runtime_status":"unknown","functional_test_refs":[{"json_po' + 'inter":"/devices/0/functional_tests/0"}],"functional_tests":[{"capability":"display-mode","statu' + 's":"not-run"}]}],"environment":{"architecture":"x86_64","boot_mode":"unknown","kernel_release":"' +
    '6.12.0-example","virtualization":"qemu"},"execution":{"backend_invoked":false,"disk_access_perfo' + 'rmed":false,"dry_run":true,"mutations_authorized":false,"plan_confirmable":false},"plan_mode":"d' + 'ry-run","plan_readiness":{"confirmable":false,"missing_required_roles":["boot-path","input"],"re' +
    'quired_user_actions":["storage-install-target"],"role_coverage":{"boot-path":"not-collected","in' + 'put":"not-collected","primary-display":"observed"}},"plan_sha256":"4f56d50f702d082670c4776c934ec' + '69b3322eabe04528fa22a62d49f7e8c868f","plan_status":"diagnostic-only","plan_version":"0.1.0","pro' +
    'file_evidence":null,"source_report":{"report_id":"example-unknown-20261125-c3","schema_version":' + '"1.0.0","sha256":"eb34865f72a09cc238d096bdefb374c03baa2b2064ad983016f16e0ff7790f10"},"warnings":' + '["no verified hardware profile evidence for this machine; the plan remains diagnostic-only","Dis' +
    'play support is unknown; no failure has been established.","required role ''boot-path'' is not rep' + 'resented in the report; plan remains diagnostic-only","required role ''input'' is not represented ' + 'in the report; plan remains diagnostic-only","storage target is not selected by hardware discove' +
    'ry; explicit user selection and immediate identity revalidation are still required"]}');
    ExpectStr('J04 plan_sha256', Plan.PlanSha256, '4f56d50f702d082670c4776c934ec69b3322eabe04528fa22a62d49f7e8c868f');
    ExpectStr('J04 blockers', JoinStrings(Plan.Blockers), 'display-0001: required critical device discovery is unknown');
    ExpectStr('J04 warnings', JoinStrings(Plan.Warnings), 'no verified hardware profile evidence for this machine; the plan remains diagnostic-only' + #1 + 'Display support is unknown; no failure has been established.' +
    #1 + 'required role ''boot-path'' is not represented in the report; plan remains diagnostic-only' + #1 +
    'required role ''input'' is not represented in the report; plan remains diagnostic-only' + #1 + 'storage target is not selected by hardware discovery; explicit user selection and immediate iden' +
    'tity revalidation are still required');
    ExpectStr('J04 summary', SummarizeReport(Report), 'WSM hardware preflight — report example-unknown-20261125-c3' + #10 + 'Schema: 1.0.0 | collected: 2026-11-25T13:47:00Z' +
    #10 + 'Environment: x86_64 | kernel 6.12.0-example | boot unknown | virtualization qemu' + #10 +
    'Devices: 1 total, 0 discovered, 1 unknown' + #10 + '- display: display-0001; discovery=unknown; driver=unknown; firmware=unknown; tests=[display-mod' +
    'e=not-run]; source=unknown' + #10 + 'Report warnings: Display support is unknown; no failure has been established.');
  end

  { J05: critical firmware missing blocks; non-critical firmware warns; a passing network test suppresses the offline warning; a duplicated report warning is dropped }
  Raw := SynthText;
  Report := JsonToReport(ParseJsonText(SynthText));
  Prov := Default(TProfileProvenance);
  if not BuildPlan(Report, SHA256Hexa(Raw), 'guix', Prov, Plan, BackendError) then
    Fail('J05', 'unexpected backend error: ' + BackendError)
  else
  begin
    ExpectStr('J05 canonical', Plan.CanonicalJson, '{"backend":{"id":"guix-system"},"blockers":["gpu-0001: required runtime firmware is missing"],"d' + 'evice_summary":[{"category":"gpu","criticality":["primary-display"],"device_id":"gpu-0001","disc' + 'overy_status":"discovered","driver_status":"bound","evidence_refs":[],"firmware_requirement":"re' +
    'quired","firmware_runtime_status":"missing","functional_test_refs":[],"functional_tests":[]},{"c' + 'ategory":"network","criticality":["network-installation"],"device_id":"net-0002","discovery_stat' + 'us":"discovered","driver_status":"bound","evidence_refs":[{"json_pointer":"/devices/1/evidence/0' +
    '"}],"firmware_requirement":"required","firmware_runtime_status":"missing","functional_test_refs"' + ':[{"json_pointer":"/devices/1/functional_tests/0"}],"functional_tests":[{"capability":"network-l' + 'ink","status":"passed"}]},{"category":"storage-device","criticality":["boot-path"],"device_id":"' +
    'ssd-0001","discovery_status":"discovered","driver_status":"bound","evidence_refs":[{"json_pointe' + 'r":"/devices/2/evidence/0"},{"json_pointer":"/devices/2/evidence/1"}],"firmware_requirement":"no' + 't-required","firmware_runtime_status":"not-needed","functional_test_refs":[],"functional_tests":' +
    '[]},{"category":"input","criticality":["input"],"device_id":"kbd-0001","discovery_status":"disco' + 'vered","driver_status":"bound","evidence_refs":[],"firmware_requirement":"not-required","firmwar' + 'e_runtime_status":"not-needed","functional_test_refs":[{"json_pointer":"/devices/3/functional_te' +
    'sts/0"}],"functional_tests":[{"capability":"input-event","status":"passed"}]}],"environment":{"a' + 'rchitecture":"x86_64","boot_mode":"uefi","kernel_release":"6.12.0-synthetic","virtualization":"n' + 'one-detected"},"execution":{"backend_invoked":false,"disk_access_performed":false,"dry_run":true' +
    ',"mutations_authorized":false,"plan_confirmable":false},"plan_mode":"dry-run","plan_readiness":{' + '"confirmable":false,"missing_required_roles":[],"required_user_actions":["storage-install-target' + '"],"role_coverage":{"boot-path":"observed","input":"observed","primary-display":"observed"}},"pl' +
    'an_sha256":"de8f65982a13ec510d80f7a2fbde1c080ae334fad7ea761d6b9353187de3e9bb","plan_status":"dia' + 'gnostic-only","plan_version":"0.1.0","profile_evidence":null,"source_report":{"report_id":"synth' + 'etic-critical-firmware","schema_version":"1.0.0","sha256":"2c59453e6b95ece0ba14eac0b543096c8e291' +
    'cee0986ced7af1635760475cadc"},"warnings":["no verified hardware profile evidence for this machin' + 'e; the plan remains diagnostic-only","net-0002: required runtime firmware is missing","a report ' + 'note that survives unchanged","storage target is not selected by hardware discovery; explicit us' +
    'er selection and immediate identity revalidation are still required"]}');
    ExpectStr('J05 plan_sha256', Plan.PlanSha256, 'de8f65982a13ec510d80f7a2fbde1c080ae334fad7ea761d6b9353187de3e9bb');
    ExpectStr('J05 blockers', JoinStrings(Plan.Blockers), 'gpu-0001: required runtime firmware is missing');
    ExpectStr('J05 warnings', JoinStrings(Plan.Warnings), 'no verified hardware profile evidence for this machine; the plan remains diagnostic-only' + #1 + 'net-0002: required runtime firmware is missing' +
    #1 + 'a report note that survives unchanged' + #1 +
    'storage target is not selected by hardware discovery; explicit user selection and immediate iden' + 'tity revalidation are still required');
    ExpectStr('J05 summary', SummarizeReport(Report), 'WSM hardware preflight — report synthetic-critical-firmware' + #10 + 'Schema: 1.0.0 | collected: 2026-11-28T00:00:00Z' +
    #10 + 'Environment: x86_64 | kernel 6.12.0-synthetic | boot uefi | virtualization none-detected' + #10 +
    'Devices: 4 total, 4 discovered, 0 unknown' + #10 + '- gpu: gpu-0001; discovery=discovered; driver=bound; firmware=missing; tests=[none]; source=unkn' +
    'own' + #10 + '- network: net-0002; discovery=discovered; driver=bound; firmware=missing; tests=[network-link=p' +
    'assed]; source=synthetic @ 2026-11-28T00:00:00Z (high)' + #10 + '- storage-device: ssd-0001; discovery=discovered; driver=bound; firmware=not-needed; tests=[none' +
    ']; source=synthetic-a @ 2026-11-28T00:00:00Z (medium)' + #10 + '- input: kbd-0001; discovery=discovered; driver=bound; firmware=not-needed; tests=[input-event=p' +
    'assed]; source=unknown' + #10 + 'Report warnings: no verified hardware profile evidence for this machine; the plan remains diagno' +
    'stic-only; a report note that survives unchanged');
  end

  { J06: desktop-observed.json with a valid profile-evidence bundle }
  Report := LoadReport(Root + '/tests/fixtures/hardware/desktop-observed.json', Raw);
  Prov := Default(TProfileProvenance);
  Prov.Present := True;
  Prov.Slug := 'test/fixture';
  Prov.ReportID := 'example-desktop-20261125-a1';
  Prov.ReportSchemaVersion := '1.0.0';
  Prov.Sha256 := 'a19bf03f5a6879d905dd21a119e40ff651e4f2af6ee375facf36eeff3402157f';
  if not BuildPlan(Report, SHA256Hexa(Raw), 'guix', Prov, Plan, BackendError) then
    Fail('J06', 'unexpected backend error: ' + BackendError)
  else
  begin
    ExpectStr('J06 canonical', Plan.CanonicalJson, '{"backend":{"id":"guix-system"},"blockers":[],"device_summary":[{"category":"gpu","criticality":' + '["primary-display"],"device_id":"dev-0001","discovery_status":"discovered","driver_status":"boun' + 'd","evidence_refs":[{"json_pointer":"/devices/0/evidence/0"}],"firmware_requirement":"unknown","' +
    'firmware_runtime_status":"unknown","functional_test_refs":[],"functional_tests":[]},{"category":' + '"display","criticality":["primary-display"],"device_id":"dev-0002","discovery_status":"discovere' + 'd","driver_status":"not-applicable","evidence_refs":[{"json_pointer":"/devices/1/evidence/0"}],"' +
    'firmware_requirement":"not-required","firmware_runtime_status":"not-needed","functional_test_ref' + 's":[],"functional_tests":[]}],"environment":{"architecture":"x86_64","boot_mode":"uefi","kernel_' + 'release":"6.12.0-example","virtualization":"none-detected"},"execution":{"backend_invoked":false' +
    ',"disk_access_performed":false,"dry_run":true,"mutations_authorized":false,"plan_confirmable":fa' + 'lse},"plan_mode":"dry-run","plan_readiness":{"confirmable":false,"missing_required_roles":["boot' + '-path","input"],"required_user_actions":["storage-install-target"],"role_coverage":{"boot-path":' +
    '"not-collected","input":"not-collected","primary-display":"observed"}},"plan_sha256":"277170b751' + '538c82bfb5d28580ccd2b54b4d78cc4f4783f87f222b004ac2a9e0","plan_status":"diagnostic-only","plan_ve' + 'rsion":"0.1.0","profile_evidence":{"report_id":"example-desktop-20261125-a1","report_schema_vers' +
    'ion":"1.0.0","sha256":"a19bf03f5a6879d905dd21a119e40ff651e4f2af6ee375facf36eeff3402157f","slug":' + '"test/fixture"},"source_report":{"report_id":"example-desktop-20261125-a1","schema_version":"1.0' + '.0","sha256":"cf7d17d42c66afe674224553b969d94bf9ef57bfe3ce779805e73b694b787b33"},"warnings":["re' +
    'quired role ''boot-path'' is not represented in the report; plan remains diagnostic-only","require' + 'd role ''input'' is not represented in the report; plan remains diagnostic-only","storage target i' + 's not selected by hardware discovery; explicit user selection and immediate identity revalidatio' +
    'n are still required"]}');
    ExpectStr('J06 plan_sha256', Plan.PlanSha256, '277170b751538c82bfb5d28580ccd2b54b4d78cc4f4783f87f222b004ac2a9e0');
    ExpectStr('J06 blockers', JoinStrings(Plan.Blockers), '');
    ExpectStr('J06 warnings', JoinStrings(Plan.Warnings), 'required role ''boot-path'' is not represented in the report; plan remains diagnostic-only' + #1 + 'required role ''input'' is not represented in the report; plan remains diagnostic-only' +
    #1 + 'storage target is not selected by hardware discovery; explicit user selection and immediate iden' + 'tity revalidation are still required');
    ExpectStr('J06 summary', SummarizeReport(Report), 'WSM hardware preflight — report example-desktop-20261125-a1' + #10 + 'Schema: 1.0.0 | collected: 2026-11-25T13:45:00Z' +
    #10 + 'Environment: x86_64 | kernel 6.12.0-example | boot uefi | virtualization none-detected' + #10 +
    'Devices: 2 total, 2 discovered, 0 unknown' + #10 + '- gpu: Example GPU; discovery=discovered; driver=bound; firmware=unknown; tests=[none]; source=s' +
    'ysfs:/sys/bus/pci/devices @ 2026-11-25T13:45:00Z (confirmed)' + #10 + '- display: dev-0002; discovery=discovered; driver=not-applicable; firmware=not-needed; tests=[no' +
    'ne]; source=sysfs:/sys/class/drm @ 2026-11-25T13:45:00Z (confirmed)');
  end

  { the one refusal in plan.py that is not a code but a ValueError }
  Report := LoadReport(Root + '/tests/fixtures/hardware/desktop-observed.json', Raw);
  Prov := Default(TProfileProvenance);
  if BuildPlan(Report, SHA256Hexa(Raw), 'nix', Prov, Plan, BackendError) then
    Fail('backend-refusal', 'accepted an unsupported backend')
  else
    ExpectStr('backend-refusal message', BackendError, 'unsupported backend; the first WSM preview supports only ''guix''');

  WriteLn;
  WriteLn(Checks, ' check(s), ', Failures, ' difference(s)');
  if Failures = 0 then
  begin
    WriteLn('PASS: every vector matches the Python implementation');
    Halt(0);
  end;
  WriteLn('FAIL: ', Failures, ' check(s) differ from the Python implementation');
  Halt(1);
end.
