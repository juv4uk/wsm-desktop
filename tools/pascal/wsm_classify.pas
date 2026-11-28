{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-classify, FPC edition.

  This is a native implementation of wsm_install/classification.py.
  It emits the complete hardware-classification/2 schema and never promotes
  a functional test to subsystem certification. CERTIFIED remains zero:
  report v1 has no complete coverage manifest.
}

program wsm_classify;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, fpjson, jsonparser;

const
  LevelKnown = 'known';
  LevelUnknown = 'unknown';

type
  TSubsystemMap = record
    Name: string;
    Categories: string;
  end;

const
  Subsystems: array[0..10] of TSubsystemMap = (
    (Name: 'cpu';       Categories: 'cpu'),
    (Name: 'memory';    Categories: 'memory'),
    (Name: 'storage';   Categories: 'storage-controller|storage-device'),
    (Name: 'graphics';  Categories: 'gpu|display'),
    (Name: 'network';   Categories: 'network'),
    (Name: 'audio';     Categories: 'audio'),
    (Name: 'bluetooth'; Categories: 'bluetooth'),
    (Name: 'input';     Categories: 'input'),
    (Name: 'usb';       Categories: 'usb-controller'),
    (Name: 'camera';    Categories: 'camera'),
    (Name: 'other';     Categories: 'other')
  );

function Str(Obj: TJSONObject; const Key: string): string;
begin
  Result := '';
  if (Obj <> nil) and (Obj.IndexOfName(Key) >= 0) then
    Result := Obj.Get(Key, '');
end;

function CategoryInList(const Category, Allowed: string): Boolean;
begin
  Result := Pos('|' + Category + '|', '|' + Allowed + '|') > 0;
end;

function EvidenceStateFor(Device: TJSONObject): string;
var
  Discovery, Status, Bound, Candidate: string;
  DriverData: TJSONData;
  Driver: TJSONObject;
begin
  Discovery := Str(Device, 'discovery_status');
  if Discovery = 'not-detected' then
    Exit('not-detected');
  if Discovery <> 'discovered' then
    Exit('unknown');

  DriverData := Device.Find('driver');
  if not (DriverData is TJSONObject) then
    Exit('unknown');
  Driver := TJSONObject(DriverData);

  Status := Str(Driver, 'status');
  if Status = '' then
    Status := 'unknown';
  Bound := Trim(Str(Driver, 'bound_driver'));
  Candidate := Trim(Str(Driver, 'candidate'));

  if Status = 'bound' then
  begin
    if Bound <> '' then
      Exit('driver-bound-not-tested');
    Exit('unknown');
  end;

  if (Status = 'available-only') and (Candidate <> '') then
    Exit('candidate-only');

  if (Status = 'unknown') or (Status = 'error') then
    Exit('unknown');
  Result := 'not-tested';
end;

function FailedFunctionTest(Device: TJSONObject): Boolean;
var
  TestsData: TJSONData;
  Tests: TJSONArray;
  ItemData: TJSONData;
  I: Integer;
begin
  Result := False;
  TestsData := Device.Find('functional_tests');
  if not (TestsData is TJSONArray) then
    Exit;
  Tests := TJSONArray(TestsData);
  for I := 0 to Tests.Count - 1 do
  begin
    ItemData := Tests.Items[I];
    if ItemData is TJSONObject then
      if Str(TJSONObject(ItemData), 'status') = 'failed' then
        Exit(True);
  end;
end;

function FunctionalTestState(const Status: string): string;
begin
  if Status = 'passed' then
    Exit('supported-tested');
  if Status = 'failed' then
    Exit('known-problem');
  if Status = 'not-run' then
    Exit('not-tested');
  Result := 'unknown';
end;

procedure CloneField(Source, Destination: TJSONObject; const Name: string);
var
  Value: TJSONData;
begin
  Value := Source.Find(Name);
  if Value <> nil then
    Destination.Add(Name, Value.Clone);
end;

procedure AppendFunctionalTests(Target: TJSONArray; Device: TJSONObject);
var
  TestsData, ItemData, RefData: TJSONData;
  Tests, Refs: TJSONArray;
  Item, ResultItem: TJSONObject;
  I: Integer;
  Status: string;
begin
  { Emit objects directly into the subsystem array. Do not add a per-device
    array as a child: the classification/2 schema requires a flat object list. }
  TestsData := Device.Find('functional_tests');
  if not (TestsData is TJSONArray) then
    Exit;
  Tests := TJSONArray(TestsData);

  for I := 0 to Tests.Count - 1 do
  begin
    ItemData := Tests.Items[I];
    if not (ItemData is TJSONObject) then
      Continue;
    Item := TJSONObject(ItemData);
    Status := Str(Item, 'status');
    if Status = '' then
      Status := 'unknown';

    ResultItem := TJSONObject.Create;
    if Str(Device, 'device_id') = '' then
      ResultItem.Add('device_id', '?')
    else
      ResultItem.Add('device_id', Str(Device, 'device_id'));
    if Str(Item, 'capability') = '' then
      ResultItem.Add('capability', 'unknown')
    else
      ResultItem.Add('capability', Str(Item, 'capability'));
    ResultItem.Add('reported_status', Status);
    ResultItem.Add('evidence_state', FunctionalTestState(Status));

    CloneField(Item, ResultItem, 'tested_at');
    CloneField(Item, ResultItem, 'method');
    CloneField(Item, ResultItem, 'result');
    RefData := Item.Find('evidence_refs');
    if RefData is TJSONArray then
    begin
      Refs := TJSONArray(RefData);
      ResultItem.Add('evidence_refs', Refs.Clone);
    end;
    Target.Add(ResultItem);
  end;
end;

function DeviceEvidenceFor(Device: TJSONObject): TJSONObject;
var
  DriverSource, FirmwareSource, EvidenceSource: TJSONData;
  DriverTarget, FirmwareTarget: TJSONObject;
  EvidenceTarget: TJSONArray;
begin
  Result := TJSONObject.Create;
  if Str(Device, 'device_id') = '' then
    Result.Add('device_id', '?')
  else
    Result.Add('device_id', Str(Device, 'device_id'));

  DriverSource := Device.Find('driver');
  if DriverSource is TJSONObject then
  begin
    DriverTarget := TJSONObject.Create;
    CloneField(TJSONObject(DriverSource), DriverTarget, 'status');
    CloneField(TJSONObject(DriverSource), DriverTarget, 'candidate');
    CloneField(TJSONObject(DriverSource), DriverTarget, 'module');
    CloneField(TJSONObject(DriverSource), DriverTarget, 'module_loaded');
    CloneField(TJSONObject(DriverSource), DriverTarget, 'bound_driver');
    CloneField(TJSONObject(DriverSource), DriverTarget, 'kernel_config_symbol');
    CloneField(TJSONObject(DriverSource), DriverTarget, 'notes');
    Result.Add('driver', DriverTarget);
  end;

  FirmwareSource := Device.Find('firmware');
  if FirmwareSource is TJSONObject then
  begin
    FirmwareTarget := TJSONObject.Create;
    CloneField(TJSONObject(FirmwareSource), FirmwareTarget, 'requirement');
    CloneField(TJSONObject(FirmwareSource), FirmwareTarget, 'runtime_status');
    CloneField(TJSONObject(FirmwareSource), FirmwareTarget, 'files_observed');
    CloneField(TJSONObject(FirmwareSource), FirmwareTarget, 'package_candidates');
    CloneField(TJSONObject(FirmwareSource), FirmwareTarget, 'kernel_log_evidence');
    CloneField(TJSONObject(FirmwareSource), FirmwareTarget, 'redistribution_status');
    Result.Add('firmware', FirmwareTarget);
  end;

  EvidenceSource := Device.Find('evidence');
  if EvidenceSource is TJSONArray then
  begin
    EvidenceTarget := TJSONArray(EvidenceSource).Clone as TJSONArray;
    Result.Add('evidence', EvidenceTarget);
  end;
end;

function BuildSubsystem(const Name, AllowedCategories: string;
  Devices: TJSONArray; out IsKnown: Boolean): TJSONObject;
var
  I: Integer;
  DeviceData: TJSONData;
  Device: TJSONObject;
  State, DeviceId: string;
  DeviceIds, Reasons, EvidenceStates, FunctionalTests, DeviceEvidence: TJSONArray;
  AllGood, AnyFailed: Boolean;
  Count: Integer;
begin
  DeviceIds := TJSONArray.Create;
  Reasons := TJSONArray.Create;
  EvidenceStates := TJSONArray.Create;
  FunctionalTests := TJSONArray.Create;
  DeviceEvidence := TJSONArray.Create;
  AllGood := True;
  AnyFailed := False;
  Count := 0;

  for I := 0 to Devices.Count - 1 do
  begin
    DeviceData := Devices.Items[I];
    if not (DeviceData is TJSONObject) then
      Continue;
    Device := TJSONObject(DeviceData);
    if not CategoryInList(Str(Device, 'category'), AllowedCategories) then
      Continue;

    Inc(Count);
    DeviceId := Str(Device, 'device_id');
    State := EvidenceStateFor(Device);
    DeviceIds.Add(DeviceId);
    EvidenceStates.Add(DeviceId + '=' + State);
    Reasons.Add(DeviceId + ': ' + State);
    AppendFunctionalTests(FunctionalTests, Device);
    DeviceEvidence.Add(DeviceEvidenceFor(Device));

    if not ((State = 'driver-bound-not-tested') or (State = 'candidate-only')) then
      AllGood := False;
    if FailedFunctionTest(Device) then
      AnyFailed := True;
  end;

  IsKnown := (Count > 0) and AllGood and (not AnyFailed);
  Result := TJSONObject.Create;
  Result.Add('subsystem', Name);
  if IsKnown then
    Result.Add('level', LevelKnown)
  else
    Result.Add('level', LevelUnknown);
  Result.Add('devices', DeviceIds);
  Result.Add('reasons', Reasons);
  Result.Add('coverage', 'unknown');
  if Count > 0 then
    Result.Add('observation', 'device-records-present')
  else
    Result.Add('observation', 'no-device-record');
  Result.Add('evidence_states', EvidenceStates);
  Result.Add('functional_tests', FunctionalTests);
  Result.Add('device_evidence', DeviceEvidence);

  if Count = 0 then
    Reasons.Add('no device record is present; report v1 has no coverage manifest, so absence cannot be interpreted as not-detected or not-collected');
end;

function BuildSummary(Devices: TJSONArray): TJSONObject;
var
  SubsystemArray: TJSONArray;
  Counts: TJSONObject;
  Subsystem: TJSONObject;
  I, KnownCount, UnknownCount: Integer;
  IsKnown: Boolean;
begin
  Result := TJSONObject.Create;
  Result.Add('schema', 'wsm-hardware-classification/2');

  SubsystemArray := TJSONArray.Create;
  KnownCount := 0;
  UnknownCount := 0;
  for I := Low(Subsystems) to High(Subsystems) do
  begin
    Subsystem := BuildSubsystem(Subsystems[I].Name, Subsystems[I].Categories,
      Devices, IsKnown);
    SubsystemArray.Add(Subsystem);
    if IsKnown then
      Inc(KnownCount)
    else
      Inc(UnknownCount);
  end;
  Result.Add('subsystems', SubsystemArray);

  Counts := TJSONObject.Create;
  Counts.Add('certified', 0);
  Counts.Add('known', KnownCount);
  Counts.Add('unknown', UnknownCount);
  Result.Add('counts', Counts);
  Result.Add('decision_policy', 'docs/INSTALL-CAPABILITY-MATRIX.md');
  Result.Add('note',
    'Diagnostic summary only. Report v1 has no complete coverage manifest; functional-test results apply only to their named capability. This summary does not choose an installation scenario or authorize a plan.');
end;

var
  InputText: TStringList;
  RootData, DevicesData: TJSONData;
  Root: TJSONObject;
  Devices: TJSONArray;
  Summary: TJSONObject;
begin
  if ParamCount <> 1 then
  begin
    WriteLn(StdErr, 'usage: wsm-classify REPORT.json');
    Halt(2);
  end;

  InputText := TStringList.Create;
  RootData := nil;
  Summary := nil;
  try
    try
      InputText.LoadFromFile(ParamStr(1));
    except
      on E: Exception do
      begin
        WriteLn(StdErr, 'wsm-classify: cannot read report: ', E.Message);
        Halt(3);
      end;
    end;

    try
      RootData := GetJSON(InputText.Text);
    except
      on E: Exception do
      begin
        WriteLn(StdErr, 'wsm-classify: report is not valid JSON: ', E.Message);
        Halt(4);
      end;
    end;

    if not (RootData is TJSONObject) then
    begin
      WriteLn(StdErr, 'wsm-classify: report is not a JSON object');
      Halt(4);
    end;
    Root := TJSONObject(RootData);

    DevicesData := Root.Find('devices');
    if not (DevicesData is TJSONArray) then
    begin
      WriteLn(StdErr, 'wsm-classify: report has no devices array');
      Halt(4);
    end;
    Devices := TJSONArray(DevicesData);

    Summary := BuildSummary(Devices);
    WriteLn(Summary.AsJSON);
  finally
    Summary.Free;
    RootData.Free;
    InputText.Free;
  end;
end.
