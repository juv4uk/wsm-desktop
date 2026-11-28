{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-classify, FPC edition: the diagnostic subsystem summary as a native binary.

  The contract is copied from wsm_install/classification.py, not reinvented:
    * a subsystem is KNOWN only when every observed device is either
      driver-bound-not-tested or candidate-only, and no functional test failed;
    * a functional test applies only to its named capability, so a passed test
      never certifies a subsystem;
    * CERTIFIED stays at zero - report v1 has no coverage manifest, and a
      summary that could say CERTIFIED would authorise an installation it
      cannot support.

  JSON comes from FPC's fpjson unit (Debian: fp-units-fcl): no
  external library enters the closure, which is the whole reason this exists.
}
program wsm_classify;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, fpjson, jsonparser;

const
  LevelKnown = 'KNOWN';
  LevelUnknown = 'UNKNOWN';

type
  TSubsystemMap = record
    Name: string;
    Categories: string;
  end;

const
  { Categories are separated by `|' because Pascal array-of-string constants
    inside a record constant are awkward and easy to get wrong. }
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
  if Obj.IndexOfName(Key) >= 0 then
    Result := Obj.Get(Key, '');
end;

{ The collector writes `bound_driver' for built-in drivers that have no module
  symlink. Requiring `module' here would turn every built-in driver into a
  false unknown - the exact mistake the Python module's comment warns about. }
function EvidenceStateFor(Device: TJSONObject): string;
var
  Discovery, Status, Bound, Candidate: string;
  Driver: TJSONObject;
begin
  Discovery := Str(Device, 'discovery_status');
  if Discovery = 'not-detected' then
    Exit('not-detected');
  if Discovery <> 'discovered' then
    Exit('unknown');

  if Device.IndexOfName('driver') < 0 then
    Exit('unknown');
  if not (Device.Find('driver') is TJSONObject) then
    Exit('unknown');
  Driver := TJSONObject(Device.Find('driver'));

  Status := Str(Driver, 'status');
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

function HasFailedFunction(Device: TJSONObject): Boolean;
var
  Tests: TJSONArray;
  I: Integer;
  Item: TJSONObject;
  Result2: string;
begin
  Result := False;
  if Device.IndexOfName('functional_tests') < 0 then
    Exit;
  if not (Device.Find('functional_tests') is TJSONArray) then
    Exit;
  Tests := TJSONArray(Device.Find('functional_tests'));
  for I := 0 to Tests.Count - 1 do
  begin
    if not (Tests.Items[I] is TJSONObject) then
      Continue;
    Item := TJSONObject(Tests.Items[I]);
    Result2 := Str(Item, 'result');
    if Result2 = '' then
      Result2 := Str(Item, 'status');
    if Result2 = 'failed' then
      Exit(True);
  end;
end;

function CategoryInList(const Category, Allowed: string): Boolean;
var
  Padded: string;
begin
  Padded := '|' + Allowed + '|';
  Result := Pos('|' + Category + '|', Padded) > 0;
end;

procedure EmitSubsystem(const Name, AllowedCategories: string;
  Devices: TJSONArray; var KnownCount, UnknownCount: Integer; var First: Boolean);
var
  I: Integer;
  Device: TJSONObject;
  Level, State, Ids, Observation: string;
  AllGood, AnyFailed: Boolean;
  Count: Integer;
begin
  AllGood := True;
  AnyFailed := False;
  Ids := '';
  Count := 0;

  for I := 0 to Devices.Count - 1 do
  begin
    if not (Devices.Items[I] is TJSONObject) then
      Continue;
    Device := TJSONObject(Devices.Items[I]);
    if not CategoryInList(Str(Device, 'category'), AllowedCategories) then
      Continue;

    State := EvidenceStateFor(Device);
    Inc(Count);
    if Ids <> '' then
      Ids := Ids + ',';
    Ids := Ids + '"' + Str(Device, 'device_id') + '=' + State + '"';

    if not ((State = 'driver-bound-not-tested') or (State = 'candidate-only')) then
      AllGood := False;
    if HasFailedFunction(Device) then
      AnyFailed := True;
  end;

  if Count = 0 then
  begin
    Level := LevelUnknown;
    Observation := 'no-device-record';
  end
  else
  begin
    Observation := 'device-records-present';
    if AllGood and not AnyFailed then
      Level := LevelKnown
    else
      Level := LevelUnknown;
  end;

  if not First then
    Write(',');
  First := False;
  Write('{"subsystem":"', Name, '","level":"', Level, '"');
  Write(',"observation":"', Observation, '"');
  Write(',"evidence_states":[', Ids, ']}');

  if Level = LevelKnown then
    Inc(KnownCount)
  else
    Inc(UnknownCount);
end;

var
  Text: TStringList;
  Parser: TJSONParser;
  Root: TJSONObject;
  Devices: TJSONArray;
  First: Boolean;
  KnownCount, UnknownCount: Integer;
  I: Integer;
begin
  if ParamCount <> 1 then
  begin
    WriteLn(StdErr, 'usage: wsm-classify REPORT.json');
    Halt(2);
  end;

  Text := TStringList.Create;
  try
    try
      Text.LoadFromFile(ParamStr(1));
    except
      on E: Exception do
      begin
        WriteLn(StdErr, 'wsm-classify: cannot read ', ParamStr(1), ': ', E.Message);
        Halt(3);
      end;
    end;

    Parser := nil;
    try
      try
        Parser := TJSONParser.Create(Text.Text);
        if not (Parser.Parse is TJSONObject) then
        begin
          WriteLn(StdErr, 'wsm-classify: report is not a JSON object');
          Halt(4);
        end;
        Root := TJSONObject(Parser.Parse);
      except
        on E: Exception do
        begin
          WriteLn(StdErr, 'wsm-classify: report is not valid JSON: ', E.Message);
          Halt(4);
        end;
      end;

      if Root.IndexOfName('devices') < 0 then
      begin
        WriteLn(StdErr, 'wsm-classify: report has no devices array');
        Halt(4);
      end;
      if not (Root.Find('devices') is TJSONArray) then
      begin
        WriteLn(StdErr, 'wsm-classify: devices is not an array');
        Halt(4);
      end;
      Devices := TJSONArray(Root.Find('devices'));

      KnownCount := 0;
      UnknownCount := 0;
      First := True;
      Write('{"schema":"wsm-hardware-classification/2","subsystems":[');
      for I := Low(Subsystems) to High(Subsystems) do
        EmitSubsystem(Subsystems[I].Name, Subsystems[I].Categories,
                      Devices, KnownCount, UnknownCount, First);
      Write(']');
      Write(',"counts":{"CERTIFIED":0,"KNOWN":', KnownCount,
            ',"UNKNOWN":', UnknownCount, '}');
      Write(',"note":"Diagnostic summary only. Report v1 has no complete ');
      Write('coverage manifest; functional-test results apply only to their ');
      Write('named capability. This summary does not authorise a plan."');
      WriteLn('}');
    finally
      Parser.Free;
    end;
  finally
    Text.Free;
  end;
end.
