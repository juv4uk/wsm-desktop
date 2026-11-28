{ SPDX-License-Identifier: LicenseRef-Volnist }
{ }
{ wsm-hwcheck-pascal — перший FPC-зріз колектора доказів. }
{ }
{ ЦЕ ПЕРШИЙ ЗРІЗ, А НЕ ЗАМІНА Python-колектора. Він охоплює архітектуру, }
{ kernel release та PCI identity + прямі факти прив'язки драйвера/модуля. }
{ Діагностика firmware, модулів, ISA, USB, block, DRM і повний report schema }
{ лишаються поза цим зрізом, доки для кожного блоку не буде паритетного тесту. }
{ }
{ Джерела: uname(2), sysfs PCI. Жодних зовнішніх команд, мережі, MMIO, }
{ завантаження модулів або запису. }
{ }
{ У середовищі написання FPC не встановлено. Реальна збірка і runtime parity }
{ виконуються pinned FPC 3.2.2 у .github/workflows/fpc-build.yml. }
{ }
{ Compile: fpc -O2 -Mobjfpc -Sh tools/fpc/wsm_hwcheck.pas }

program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix, Unix;

const
  SysRoot = '/sys';

type
  TDevice = record
    Address: string;      { 0000:01:00.0 }
    Vendor: string;       { raw sysfs value, e.g. 0x10de }
    Device: string;       { raw sysfs value, e.g. 0x1c82 }
    ClassCode: string;    { raw sysfs value, e.g. 0x030200 }
    Driver: string;       { bound driver basename, if present }
    Module: string;       { loadable module basename, if present }
  end;

var
  Devices: array of TDevice;

function ReadFirstLine(const Path: string): string;
var
  Stream: TFileStream;
  Buffer: array[0..1023] of Char;
  ReadCount: LongInt;
begin
  Result := '';
  if not FileExists(Path) then
    Exit;
  try
    Stream := TFileStream.Create(Path, fmOpenRead or fmShareDenyNone);
  except
    Exit;
  end;
  try
    ReadCount := Stream.Read(Buffer, SizeOf(Buffer) - 1);
    if ReadCount > 0 then
    begin
      Buffer[ReadCount] := #0;
      Result := Trim(string(PChar(@Buffer[0])));
    end;
  finally
    Stream.Free;
  end;
end;

procedure ReadSystemIdentity(out Architecture, KernelRelease: string);
var
  SystemName: UtsName;
begin
  Architecture := 'unknown';
  KernelRelease := 'unknown';
  FillChar(SystemName, SizeOf(SystemName), 0);
  if fpUname(SystemName) <> 0 then
    Exit;
  if SystemName.Machine[0] <> #0 then
    Architecture := StrPas(@SystemName.Machine[0]);
  if SystemName.Release[0] <> #0 then
    KernelRelease := StrPas(@SystemName.Release[0]);
end;

{ A driver binding is a sysfs symlink. fpReadLink reads the link itself and
  never executes a shell or follows a user-provided command. }
function ReadDriverLink(const DevicePath: string): string;
var
  LinkTarget: array[0..1023] of Char;
  Count: LongInt;
begin
  Result := '';
  FillChar(LinkTarget, SizeOf(LinkTarget), 0);
  Count := fpReadLink(DevicePath + '/driver', @LinkTarget[0], SizeOf(LinkTarget) - 1);
  if Count <= 0 then
    Exit;
  LinkTarget[Count] := #0;
  Result := ExtractFileName(string(PChar(@LinkTarget[0])));
end;

{ A built-in driver has no driver/module link. That is not an error and must
  not be misreported as "driver missing". }
function ReadModuleLink(const DevicePath: string): string;
var
  LinkTarget: array[0..1023] of Char;
  Count: LongInt;
begin
  Result := '';
  FillChar(LinkTarget, SizeOf(LinkTarget), 0);
  Count := fpReadLink(DevicePath + '/driver/module', @LinkTarget[0], SizeOf(LinkTarget) - 1);
  if Count <= 0 then
    Exit;
  LinkTarget[Count] := #0;
  Result := ExtractFileName(string(PChar(@LinkTarget[0])));
end;

procedure SortPciDevices;
var
  Index, InsertAt: Integer;
  Item: TDevice;
begin
  { sysfs enumeration order is not an API. Match Python's sorted(root.iterdir()). }
  for Index := 1 to High(Devices) do
  begin
    Item := Devices[Index];
    InsertAt := Index - 1;
    while InsertAt >= 0 do
    begin
      if Devices[InsertAt].Address <= Item.Address then
        Break;
      Devices[InsertAt + 1] := Devices[InsertAt];
      Dec(InsertAt);
    end;
    Devices[InsertAt + 1] := Item;
  end;
end;

procedure ScanPciDevices;
var
  Dir: TSearchRec;
  DevicePath, Address, VendorId, DeviceId: string;
begin
  SetLength(Devices, 0);
  { PCI functions under /sys/bus/pci/devices are symlinks to device directories.
    faAnyFile alone omits symlinks on Unix, so include faSymLink explicitly. }
  if FindFirst(SysRoot + '/bus/pci/devices/*', faAnyFile or faSymLink, Dir) <> 0 then
    Exit;
  try
    repeat
      if (Dir.Name = '.') or (Dir.Name = '..') then
        Continue;
      Address := Dir.Name;
      DevicePath := SysRoot + '/bus/pci/devices/' + Address;
      if not DirectoryExists(DevicePath) then
        Continue;

      VendorId := ReadFirstLine(DevicePath + '/vendor');
      DeviceId := ReadFirstLine(DevicePath + '/device');
      { Match Python _pci_devices(): ignore entries with neither identity field. }
      if (VendorId = '') and (DeviceId = '') then
        Continue;

      SetLength(Devices, Length(Devices) + 1);
      Devices[High(Devices)].Address := Address;
      Devices[High(Devices)].Vendor := VendorId;
      Devices[High(Devices)].Device := DeviceId;
      Devices[High(Devices)].ClassCode := ReadFirstLine(DevicePath + '/class');
      Devices[High(Devices)].Driver := ReadDriverLink(DevicePath);
      Devices[High(Devices)].Module := ReadModuleLink(DevicePath);
    until FindNext(Dir) <> 0;
  finally
    FindClose(Dir);
  end;
  SortPciDevices;
end;

function JsonEscape(const Value: string): string;
var
  Index: Integer;
  Character: Char;
begin
  Result := '';
  for Index := 1 to Length(Value) do
  begin
    Character := Value[Index];
    case Character of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #8: Result := Result + '\b';
      #9: Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
    else
      if Character < ' ' then
        Result := Result + '\u' + IntToHex(Ord(Character), 4)
      else
        Result := Result + Character;
    end;
  end;
end;

function DriverJson(const Device: TDevice): string;
begin
  if Device.Driver = '' then
    Exit('{"status":"none-known"}');

  Result := '{"status":"bound","bound_driver":"' +
    JsonEscape(Device.Driver) + '"';

  if Device.Module <> '' then
    Result := Result + ',"module":"' + JsonEscape(Device.Module) +
      '","module_loaded":true';

  Result := Result + '}';
end;

procedure EmitReport;
var
  Index: Integer;
  Architecture, KernelRelease, Separator: string;
begin
  ReadSystemIdentity(Architecture, KernelRelease);
  WriteLn('{');
  WriteLn('  "collector": "wsm-hwcheck-pascal",');
  WriteLn('  "environment": {');
  WriteLn('    "architecture": "', JsonEscape(Architecture), '",');
  WriteLn('    "kernel_release": "', JsonEscape(KernelRelease), '"');
  WriteLn('  },');
  WriteLn('  "pci": [');

  Separator := '';
  for Index := 0 to High(Devices) do
  begin
    WriteLn(Separator, '    {');
    WriteLn('      "address": "', JsonEscape(Devices[Index].Address), '",');
    WriteLn('      "vendor": "', JsonEscape(Devices[Index].Vendor), '",');
    WriteLn('      "device": "', JsonEscape(Devices[Index].Device), '",');
    WriteLn('      "class": "', JsonEscape(Devices[Index].ClassCode), '",');
    WriteLn('      "driver": ', DriverJson(Devices[Index]));
    Write('    }');
    Separator := ',' + LineEnding;
  end;
  if Length(Devices) > 0 then
    WriteLn;
  WriteLn('  ],');
  WriteLn('  "evidence_level": "read-only sysfs and uname; no MMIO, no module load, no write"');
  WriteLn('}');
end;

begin
  if ParamCount > 0 then
  begin
    if (ParamCount = 1) and ((ParamStr(1) = '--help') or (ParamStr(1) = '-h')) then
    begin
      WriteLn('wsm-hwcheck-pascal — read-only PCI identity evidence (first FPC slice)');
      WriteLn('usage: wsm-hwcheck-pascal');
      Halt(0);
    end;
    WriteLn(StdErr, 'wsm-hwcheck-pascal: невідомий аргумент');
    Halt(2);
  end;
  ScanPciDevices;
  EmitReport;
end.
