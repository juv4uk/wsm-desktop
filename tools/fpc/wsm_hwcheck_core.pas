// SPDX-License-Identifier: LicenseRef-Volnist
unit wsm_hwcheck_core;

{$mode objfpc}{$H+}

interface

uses
  fpjson;

const
  WSM_FPC_VERSION = '0.1.0';
  WSM_SCHEMA_VERSION = '1.1.0';

function CollectReport(const SysfsRoot, ProcRoot: string): TJSONObject;

implementation

uses
  Classes, SysUtils, DateUtils, BaseUnix;

const
  MaxReadBytes = 262144;
  MaxDevices = 4096;

function JoinPath(const A, B: string): string;
begin
  Result := IncludeTrailingPathDelimiter(A) + B;
end;

function ReadFile(const Path: string; const Limit: SizeInt = MaxReadBytes): string;
var
  Stream: TFileStream;
  Buffer: array[0..4095] of Byte;
  Count, Current, Request: SizeInt;
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
    while Length(Result) < Limit do
    begin
      Request := SizeOf(Buffer);
      if Request > Limit - Length(Result) then
        Request := Limit - Length(Result);
      Count := Stream.Read(Buffer, Request);
      if Count <= 0 then
        Break;
      Current := Length(Result);
      SetLength(Result, Current + Count);
      Move(Buffer[0], Result[Current + 1], Count);
    end;
  finally
    Stream.Free;
  end;
end;

function ReadValue(const Path: string): string;
begin
  Result := Trim(ReadFile(Path, 8192));
  if (Result = '') or SameText(Result, 'unknown') or
     SameText(Result, 'none') or SameText(Result, 'n/a') then
    Result := '';
end;

function CleanValue(const Value: string): string;
begin
  Result := Trim(Value);
  if (Result = '') or SameText(Result, 'unknown') or
     SameText(Result, 'none') or SameText(Result, 'n/a') or
     SameText(Result, 'to be filled by o.e.m.') or
     SameText(Result, 'to be filled by oem') or
     SameText(Result, 'default string') then
    Result := '';
end;

function ReadInteger(const Path: string; out Value: Int64): Boolean;
var
  TextValue: string;
begin
  TextValue := ReadValue(Path);
  Result := (TextValue <> '') and TryStrToInt64(TextValue, Value);
end;

function ReadBoolean(const Path: string; out Value: Boolean): Boolean;
var
  TextValue: string;
begin
  TextValue := LowerCase(ReadValue(Path));
  Result := True;
  if (TextValue = '1') or (TextValue = 'y') or (TextValue = 'yes') then
    Value := True
  else if (TextValue = '0') or (TextValue = 'n') or (TextValue = 'no') then
    Value := False
  else
    Result := False;
end;

function ReadLinkName(const Path: string): string;
var
  Buffer: array[0..1023] of Char;
  Count: SizeInt;
begin
  Result := '';
  FillChar(Buffer, SizeOf(Buffer), 0);
  { fpReadLink приймає pchar. FPC у багатьох випадках вставляє неявне
    перетворення AnsiString→PChar, але покладатися на це не варто: явне
    PChar(Path) читається однозначно і не залежить від режиму {$H+} та
    версії компілятора. }
  Count := fpReadLink(PChar(Path), @Buffer[0], SizeOf(Buffer) - 1);
  if Count <= 0 then
    Exit;
  Buffer[Count] := #0;
  Result := ExtractFileName(StrPas(@Buffer[0]));
end;

{ NormalizeHexId видалено: identity зберігає сирі значення sysfs, як і
  Python-колектор. Нормалізація потрібна лише для пошуку в pci.ids, і коли
  такий пошук з'явиться тут, функцію треба буде повернути поруч із ним. }

function CurrentTimestampUTC: string;
var
  UnixTime: Int64;
  UTCDate: TDateTime;
begin
  UnixTime := DateTimeToUnix(Now, False);
  UTCDate := UnixToDateTime(UnixTime, True);
  Result := FormatDateTime('yyyy"-"mm"-"dd"T"hh":"nn":"ss"Z"', UTCDate);
end;

function NewReportId: string;
var
  Index: Integer;
  RandomBytes: array[0..15] of Byte;
  Stream: TFileStream;
begin
  FillChar(RandomBytes, SizeOf(RandomBytes), 0);
  try
    Stream := TFileStream.Create('/dev/urandom', fmOpenRead or fmShareDenyNone);
    try
      Stream.ReadBuffer(RandomBytes, SizeOf(RandomBytes));
    finally
      Stream.Free;
    end;
  except
    { A report ID is not a security token; retain a local-only fallback if
      the platform has no readable entropy device. }
    Randomize;
    for Index := Low(RandomBytes) to High(RandomBytes) do
      RandomBytes[Index] := Random(256);
  end;

  { Python: 'wsm-' + secrets.token_hex(12) — 12 байтів, тобто 24 символи, і
    в нижньому регістрі. IntToHex дає верхній, тому LowerCase обовʼязковий:
    інакше report_id відрізняється від Python уже на першому символі. }
  Result := 'wsm-';
  for Index := Low(RandomBytes) to 11 do
    Result := Result + LowerCase(IntToHex(RandomBytes[Index], 2));
end;

function ArchitectureName: string;
begin
  {$if defined(CPUX86_64)}
  Result := 'x86_64';
  {$elseif defined(CPUI386)}
  Result := 'i686';
  {$elseif defined(CPUAARCH64)}
  Result := 'aarch64';
  {$elseif defined(CPUARM)}
  Result := 'arm';
  {$elseif defined(CPUPPC64)}
  Result := 'ppc64';
  {$else}
  Result := 'unknown';
  {$endif}
end;

{ Імена записів каталогу в тому ж порядку, що й у Python: відсортовані.
  FindFirst віддає порядок readdir, а collector.py робить
  sorted(root.iterdir()), тому без сортування текстовий паритет не зійшовся б
  на машині з двома й більше пристроями. }
procedure ListSortedEntries(const Directory: string; Names: TStringList);
var
  Search: TSearchRec;
begin
  Names.Clear;
  Names.Sorted := True;
  Names.Duplicates := dupIgnore;
  if FindFirst(JoinPath(Directory, '*'), faAnyFile, Search) <> 0 then
    Exit;
  try
    repeat
      if (Search.Name = '.') or (Search.Name = '..') then
        Continue;
      Names.Add(Search.Name);
    until FindNext(Search) <> 0;
  finally
    FindClose(Search);
  end;
end;

procedure AddIfPresent(Target: TJSONObject; const Name, Value: string);
begin
  if Value <> '' then
    Target.Add(Name, Value);
end;

procedure AddUnavailable(Target: TJSONArray; const Name: string);
begin
  Target.Add(Name);
end;

function NewEvidence(const Source, Summary, ObservedAt: string): TJSONObject;
begin
  Result := TJSONObject.Create;
  Result.Add('kind', 'live-observation');
  Result.Add('source', Source);
  Result.Add('observed_at', ObservedAt);
  Result.Add('confidence', 'confirmed');
  Result.Add('summary', Summary);
end;

function NewDriverFacts(const DevicePath: string): TJSONObject;
var
  DriverName, ModuleName: string;
begin
  Result := TJSONObject.Create;
  if not DirectoryExists(DevicePath) then
  begin
    Result.Add('status', 'unknown');
    Exit;
  end;

  DriverName := ReadLinkName(JoinPath(DevicePath, 'driver'));
  if DriverName = '' then
  begin
    Result.Add('status', 'none-known');
    Result.Add('notes',
      'No driver symlink is present in sysfs for this device at collection time.');
    Exit;
  end;

  Result.Add('status', 'bound');
  Result.Add('bound_driver', DriverName);
  ModuleName := ReadLinkName(JoinPath(JoinPath(DevicePath, 'driver'), 'module'));
  if ModuleName <> '' then
  begin
    Result.Add('module', ModuleName);
    Result.Add('module_loaded', True);
  end;
end;

function NewBaseDevice(const DeviceId, Category, Bus, Source, Summary,
  ObservedAt: string; Driver: TJSONObject): TJSONObject;
var
  { Розділено навмисно: TJSONData не має методу Add — він є лише в
    TJSONObject і TJSONArray. Спільна змінна типу TJSONData робила
    Evidence.Add(...) помилкою компіляції, і жодне приведення типу
    цього не лікувало. }
  Firmware: TJSONObject;
  Tests, Evidence, Recommendations: TJSONArray;
begin
  Result := TJSONObject.Create;
  Result.Add('device_id', DeviceId);
  Result.Add('category', Category);
  Result.Add('bus', Bus);
  Result.Add('discovery_status', 'discovered');
  if Driver = nil then
  begin
    Driver := TJSONObject.Create;
    if (Category = 'cpu') or (Category = 'motherboard') or (Category = 'display') then
      Driver.Add('status', 'not-applicable')
    else
      Driver.Add('status', 'unknown');
  end;
  Result.Add('driver', Driver);

  Firmware := TJSONObject.Create;
  Firmware.Add('requirement', 'unknown');
  Firmware.Add('runtime_status', 'unknown');
  Firmware.Add('redistribution_status', 'unknown');
  Result.Add('firmware', Firmware);

  Tests := TJSONArray.Create;
  Result.Add('functional_tests', Tests);

  Evidence := TJSONArray.Create;
  Evidence.Add(NewEvidence(Source, Summary, ObservedAt));
  Result.Add('evidence', Evidence);

  Recommendations := TJSONArray.Create;
  Result.Add('recommendations', Recommendations);
end;

function NormalizeBiosDate(const Value: string): string;
var
  MonthValue, DayValue, YearValue: Integer;
  ParsedDate: TDateTime;
begin
  Result := '';
  if (Length(Value) <> 10) or (Value[3] <> '/') or (Value[6] <> '/') then
    Exit;
  if not TryStrToInt(Copy(Value, 1, 2), MonthValue) or
     not TryStrToInt(Copy(Value, 4, 2), DayValue) or
     not TryStrToInt(Copy(Value, 7, 4), YearValue) then
    Exit;
  if (YearValue < 1990) or (YearValue > YearOf(Now) + 1) then
    Exit;
  if not TryEncodeDate(Word(YearValue), Word(MonthValue), Word(DayValue), ParsedDate) then
    Exit;
  Result := FormatDateTime('yyyy"-"mm"-"dd', ParsedDate);
end;

function CollectPlatform(const SysfsRoot: string): TJSONObject;
const
  SourceNames: array[0..7] of string = (
    'sys_vendor', 'product_name', 'board_vendor', 'board_name',
    'board_version', 'bios_vendor', 'bios_version', 'bios_release'
  );
  JsonNames: array[0..7] of string = (
    'system_vendor', 'product_name', 'board_vendor', 'board_name',
    'board_version', 'bios_vendor', 'bios_version', 'bios_release'
  );
var
  Index: Integer;
  Value, DateValue: string;
  DmiRoot: string;
begin
  Result := TJSONObject.Create;
  DmiRoot := JoinPath(SysfsRoot, 'class/dmi/id');
  for Index := Low(SourceNames) to High(SourceNames) do
  begin
    Value := CleanValue(ReadValue(JoinPath(DmiRoot, SourceNames[Index])));
    if Value <> '' then
      Result.Add(JsonNames[Index], Value);
  end;
  DateValue := NormalizeBiosDate(ReadValue(JoinPath(DmiRoot, 'bios_date')));
  AddIfPresent(Result, 'bios_date', DateValue);
end;

function DetectBootMode(const SysfsRoot: string; const Architecture: string;
  out Evidence: string): string;
var
  DmiRoot: string;
  DmiIdentityAvailable: Boolean;
begin
  Evidence := '';
  if DirectoryExists(JoinPath(SysfsRoot, 'firmware/efi')) then
  begin
    Evidence := 'sysfs:/firmware/efi is present: the kernel was booted through EFI.';
    Exit('uefi');
  end;
  DmiRoot := JoinPath(SysfsRoot, 'class/dmi/id');
  DmiIdentityAvailable :=
    (CleanValue(ReadValue(JoinPath(DmiRoot, 'sys_vendor'))) <> '') or
    (CleanValue(ReadValue(JoinPath(DmiRoot, 'product_name'))) <> '') or
    (CleanValue(ReadValue(JoinPath(DmiRoot, 'board_name'))) <> '') or
    (CleanValue(ReadValue(JoinPath(DmiRoot, 'board_vendor'))) <> '');
  if ((Architecture = 'x86_64') or (Architecture = 'i686')) and
     DmiIdentityAvailable then
  begin
    Evidence := 'sysfs:/firmware/efi is absent while x86 DMI identity is present; legacy BIOS/CSM handoff is observed.';
    Exit('bios');
  end;
  Evidence := 'Neither sysfs:/firmware/efi nor sufficient platform identity is available; boot mode is unknown.';
  Result := 'unknown';
end;

function DetectVirtualization(const SysfsRoot: string; Platform: TJSONObject): string;
var
  Hypervisor, Combined: string;
begin
  Hypervisor := LowerCase(ReadValue(JoinPath(SysfsRoot, 'hypervisor/type')));
  if Pos('kvm', Hypervisor) > 0 then
    Exit('kvm');
  if Pos('xen', Hypervisor) > 0 then
    Exit('xen');

  Combined := '';
  if Platform.IndexOfName('system_vendor') >= 0 then
    Combined := Combined + ' ' + LowerCase(Platform.Get('system_vendor', ''));
  if Platform.IndexOfName('product_name') >= 0 then
    Combined := Combined + ' ' + LowerCase(Platform.Get('product_name', ''));
  if Platform.IndexOfName('board_name') >= 0 then
    Combined := Combined + ' ' + LowerCase(Platform.Get('board_name', ''));

  if (Pos('qemu', Combined) > 0) or (Pos('kvm', Combined) > 0) then
    Exit('qemu');
  if Pos('vmware', Combined) > 0 then
    Exit('vmware');
  if (Pos('virtualbox', Combined) > 0) or (Pos('innotek', Combined) > 0) then
    Exit('other');
  if (Pos('virtual machine', Combined) > 0) and (Pos('microsoft', Combined) > 0) then
    Exit('hyper-v');
  if Pos('xen', Combined) > 0 then
    Exit('xen');
  Result := 'unknown';
end;

function PciCategory(const ClassValue: string): string;
var
  Value: string;
begin
  Value := LowerCase(Trim(ClassValue));
  if Copy(Value, 1, 2) = '0x' then
    Delete(Value, 1, 2);
  if Copy(Value, 1, 2) = '03' then Exit('gpu');
  if Copy(Value, 1, 2) = '02' then Exit('network');
  if Copy(Value, 1, 2) = '04' then Exit('audio');
  if Copy(Value, 1, 2) = '01' then Exit('storage-controller');
  if Copy(Value, 1, 4) = '0c03' then Exit('usb-controller');
  Result := 'other';
end;

function CollectCPU(const ProcRoot, SysfsRoot, ObservedAt: string): TJSONObject;
var
  TextValue, Line, Key, Value, Model, Manufacturer: string;
  Lines: TStringList;
  Index, Separator, LogicalCount: Integer;
  Fields: array[0..4] of string;
  CPUFacts, Identity, Unavailable: TJSONObject;
  Missing: TJSONArray;
begin
  Result := nil;
  TextValue := ReadFile(JoinPath(ProcRoot, 'cpuinfo'));
  if TextValue = '' then
    Exit;

  Fields[0] := '';
  Fields[1] := '';
  Fields[2] := '';
  Fields[3] := '';
  Lines := TStringList.Create;
  try
    Lines.Text := TextValue;
    Model := '';
    Manufacturer := '';
    LogicalCount := 0;
    for Index := 0 to Lines.Count - 1 do
    begin
      Line := Lines[Index];
      Separator := Pos(':', Line);
      if Separator <= 0 then
        Continue;
      Key := Trim(Copy(Line, 1, Separator - 1));
      Value := CleanValue(Copy(Line, Separator + 1, MaxInt));
      if SameText(Key, 'processor') then
        Inc(LogicalCount);
      if Value = '' then
        Continue;
      if SameText(Key, 'model name') or SameText(Key, 'Hardware') then
        if Model = '' then Model := Value;
      if SameText(Key, 'vendor_id') or SameText(Key, 'CPU implementer') then
        if Manufacturer = '' then Manufacturer := Value;
      if SameText(Key, 'cpu family') then Fields[0] := Value;
      if SameText(Key, 'model') then Fields[1] := Value;
      if SameText(Key, 'stepping') then Fields[2] := Value;
      if SameText(Key, 'microcode') then Fields[3] := Value;
    end;
  finally
    Lines.Free;
  end;

  if (Model = '') and (Manufacturer = '') then
    Exit;

  Identity := TJSONObject.Create;
  AddIfPresent(Identity, 'model', Model);
  AddIfPresent(Identity, 'manufacturer', Manufacturer);
  Result := NewBaseDevice('cpu-0', 'cpu', 'cpu',
    'procfs:/cpuinfo', 'CPU model information was read from procfs.',
    ObservedAt, nil);
  if Identity.Count > 0 then
    Result.Add('identity', Identity)
  else
    Identity.Free;

  CPUFacts := TJSONObject.Create;
  AddIfPresent(CPUFacts, 'family', Fields[0]);
  AddIfPresent(CPUFacts, 'model_number', Fields[1]);
  AddIfPresent(CPUFacts, 'stepping', Fields[2]);
  if Fields[3] = '' then
    Fields[3] := ReadValue(JoinPath(SysfsRoot,
      'devices/system/cpu/cpu0/microcode/version'));
  AddIfPresent(CPUFacts, 'microcode', Fields[3]);
  if LogicalCount > 0 then
    CPUFacts.Add('logical_processors', LogicalCount);

  Missing := TJSONArray.Create;
  if Fields[3] = '' then Missing.Add('microcode');
  if LogicalCount <= 0 then Missing.Add('logical_processors');
  if Missing.Count > 0 then
    CPUFacts.Add('unavailable', Missing)
  else
    Missing.Free;
  if CPUFacts.Count > 0 then
    Result.Add('cpu', CPUFacts)
  else
    CPUFacts.Free;
end;

function CollectBoard(const Platform: TJSONObject; const ObservedAt: string): TJSONObject;
var
  Identity: TJSONObject;
begin
  Result := nil;
  if (Platform.IndexOfName('board_vendor') < 0) and
     (Platform.IndexOfName('board_name') < 0) then
    Exit;

  Identity := TJSONObject.Create;
  AddIfPresent(Identity, 'manufacturer', Platform.Get('board_vendor', ''));
  AddIfPresent(Identity, 'model', Platform.Get('board_name', ''));
  AddIfPresent(Identity, 'revision', Platform.Get('board_version', ''));
  Result := NewBaseDevice('platform-board-0', 'motherboard', 'platform',
    'sysfs:/class/dmi/id', 'Motherboard identity fields were read from DMI sysfs.',
    ObservedAt, nil);
  Result.Add('identity', Identity);
end;

function CollectGPUFacts(const DevicePath: string): TJSONObject;
var
  Value: Boolean;
  Number: Int64;
  LinkRoot, Name: string;
  Names: TStringList;
  Index: Integer;
  Cards, Missing: TJSONArray;
  Link: TJSONObject;
begin
  Result := TJSONObject.Create;
  Missing := TJSONArray.Create;

  if ReadBoolean(JoinPath(DevicePath, 'boot_vga'), Value) then
    Result.Add('boot_vga', Value)
  else
    Missing.Add('boot_vga');

  LinkRoot := JoinPath(DevicePath, 'drm');
  Cards := TJSONArray.Create;
  if DirectoryExists(LinkRoot) then
  begin
    Names := TStringList.Create;
    try
      ListSortedEntries(LinkRoot, Names);
      for Index := 0 to Names.Count - 1 do
      begin
        Name := Names[Index];
        if Copy(Name, 1, 4) = 'card' then
          Cards.Add(Name);
      end;
    finally
      Names.Free;
    end;
    Result.Add('drm_cards', Cards);
  end
  else
  begin
    Cards.Free;
    Missing.Add('drm_cards');
  end;

  Link := TJSONObject.Create;
  Name := ReadValue(JoinPath(DevicePath, 'current_link_speed'));
  if Name <> '' then Link.Add('current_speed', Name)
  else Missing.Add('pci_link.current_speed');
  Name := ReadValue(JoinPath(DevicePath, 'max_link_speed'));
  if Name <> '' then Link.Add('max_speed', Name)
  else Missing.Add('pci_link.max_speed');
  if ReadInteger(JoinPath(DevicePath, 'current_link_width'), Number) then
    Link.Add('current_width', Number)
  else Missing.Add('pci_link.current_width');
  if ReadInteger(JoinPath(DevicePath, 'max_link_width'), Number) then
    Link.Add('max_width', Number)
  else Missing.Add('pci_link.max_width');
  if Link.Count > 0 then Result.Add('pci_link', Link)
  else Link.Free;

  if Missing.Count > 0 then
    Result.Add('unavailable', Missing)
  else
    Missing.Free;
end;

function CollectNetworkFacts: TJSONObject;
var
  Missing, Interfaces: TJSONArray;
begin
  Result := TJSONObject.Create;
  Result.Add('status', 'unknown');
  Interfaces := TJSONArray.Create;
  Result.Add('interfaces', Interfaces);
  Missing := TJSONArray.Create;
  Missing.Add('interfaces');
  Result.Add('unavailable', Missing);
end;

procedure AddPCIDevices(const SysfsRoot, ObservedAt: string; Devices: TJSONArray);
var
  Root, EntryName, DevicePath, Vendor, Product, ClassValue, Category: string;
  Names: TStringList;
  Index: Integer;
  Identity, Device: TJSONObject;
  Count: Integer;
begin
  Root := JoinPath(SysfsRoot, 'bus/pci/devices');
  if not DirectoryExists(Root) then
    Exit;

  Names := TStringList.Create;
  try
    ListSortedEntries(Root, Names);
    Count := 0;
    for Index := 0 to Names.Count - 1 do
    begin
      EntryName := Names[Index];
      Inc(Count);
      if Count > MaxDevices then
        Break;
      DevicePath := JoinPath(Root, EntryName);
      { Python зберігає СИРЕ значення sysfs ("0x10de") у identity; _hex_id
        ("10de") там використовується лише для пошуку в pci.ids. Нормалізація
        тут зламала б паритет, тому читаємо як є. }
      Vendor := ReadValue(JoinPath(DevicePath, 'vendor'));
      Product := ReadValue(JoinPath(DevicePath, 'device'));
      if (Vendor = '') and (Product = '') then
        Continue;
      ClassValue := ReadValue(JoinPath(DevicePath, 'class'));
      Category := PciCategory(ClassValue);

      Identity := TJSONObject.Create;
      AddIfPresent(Identity, 'vendor_id', Vendor);
      AddIfPresent(Identity, 'device_id', Product);
      AddIfPresent(Identity, 'subsystem_vendor_id',
        ReadValue(JoinPath(DevicePath, 'subsystem_vendor')));
      AddIfPresent(Identity, 'subsystem_device_id',
        ReadValue(JoinPath(DevicePath, 'subsystem_device')));
      AddIfPresent(Identity, 'revision', ReadValue(JoinPath(DevicePath, 'revision')));
      AddIfPresent(Identity, 'class_id', ClassValue);
      AddIfPresent(Identity, 'modalias', ReadValue(JoinPath(DevicePath, 'modalias')));
      Identity.Add('local_path', '/bus/pci/devices/' + EntryName);

      Device := NewBaseDevice('pci-' + EntryName, Category, 'pci',
        'sysfs:/bus/pci/devices/' + EntryName,
        'PCI function and its kernel driver binding were read from sysfs.',
        ObservedAt, NewDriverFacts(DevicePath));
      Device.Add('identity', Identity);

      if Category = 'gpu' then
        Device.Add('gpu', CollectGPUFacts(DevicePath))
      else if Category = 'network' then
        Device.Add('network', CollectNetworkFacts);

      Devices.Add(Device);
    end;
  finally
    Names.Free;
  end;
end;

function USBCategory(const ClassValue: string): string;
var
  Value: string;
begin
  Value := LowerCase(ClassValue);
  if (Value = '02') or (Value = '0x02') then Exit('network');
  if (Value = '03') or (Value = '0x03') then Exit('input');
  if (Value = '08') or (Value = '0x08') then Exit('storage-device');
  if (Value = 'e0') or (Value = '0xe0') then Exit('bluetooth');
  Result := 'other';
end;

procedure AddUSBDevices(const SysfsRoot, ObservedAt: string; Devices: TJSONArray);
var
  Root, Name, DevicePath, Vendor, Product, ClassValue, Model, Manufacturer: string;
  Names: TStringList;
  Index: Integer;
  Identity, Device: TJSONObject;
begin
  Root := JoinPath(SysfsRoot, 'bus/usb/devices');
  if not DirectoryExists(Root) then
    Exit;
  Names := TStringList.Create;
  try
    ListSortedEntries(Root, Names);
    for Index := 0 to Names.Count - 1 do
    begin
      Name := Names[Index];
      DevicePath := JoinPath(Root, Name);
      { Так само, як для PCI: Python зберігає сире значення ("1d6b"), а не
        нормалізоване; idVendor у sysfs уже без 0x, тому нормалізація тут
        все одно нічого не додає. }
      Vendor := ReadValue(JoinPath(DevicePath, 'idVendor'));
      Product := ReadValue(JoinPath(DevicePath, 'idProduct'));
      if (Vendor = '') or (Product = '') then
        Continue;
      ClassValue := ReadValue(JoinPath(DevicePath, 'bDeviceClass'));
      Model := ReadValue(JoinPath(DevicePath, 'product'));
      Manufacturer := ReadValue(JoinPath(DevicePath, 'manufacturer'));

      Identity := TJSONObject.Create;
      Identity.Add('vendor_id', Vendor);
      Identity.Add('device_id', Product);
      Identity.Add('local_path', '/bus/usb/devices/' + Name);
      AddIfPresent(Identity, 'manufacturer', Manufacturer);
      AddIfPresent(Identity, 'model', Model);
      AddIfPresent(Identity, 'revision', ReadValue(JoinPath(DevicePath, 'bcdDevice')));
      AddIfPresent(Identity, 'modalias', ReadValue(JoinPath(DevicePath, 'modalias')));

      Device := NewBaseDevice('usb-' + Name, USBCategory(ClassValue), 'usb',
        'sysfs:/bus/usb/devices/' + Name,
        'USB parent identity was read; interface-level class and driver binding are not collected.',
        ObservedAt, nil);
      Device.Add('identity', Identity);
      Devices.Add(Device);
    end;
  finally
    Names.Free;
  end;
end;

function StorageTransport(const EntryName, DevicePath: string): string;
var
  Current, Subsystem: string;
  Depth: Integer;
begin
  Result := 'unknown';
  Current := DevicePath;
  for Depth := 1 to 8 do
  begin
    Subsystem := ReadLinkName(JoinPath(Current, 'subsystem'));
    if Subsystem <> '' then
    begin
      if Subsystem = 'usb' then Exit('usb');
      if Subsystem = 'nvme' then Exit('nvme');
      if Subsystem = 'ata' then Exit('sata');
      if Subsystem = 'mmc' then Exit('mmc');
      if Subsystem = 'virtio' then Exit('virtio');
      if Subsystem = 'scsi' then Exit('scsi-other');
    end;
    Current := ExtractFileDir(Current);
  end;
  if Copy(EntryName, 1, 4) = 'nvme' then Result := 'nvme'
  else if Copy(EntryName, 1, 3) = 'mmc' then Result := 'mmc';
end;

procedure AddBlockDevices(const SysfsRoot, ObservedAt: string; Devices: TJSONArray);
var
  Root, Name, EntryPath, DevicePath, Model, Vendor, Bus, Transport: string;
  Search, PartitionSearch: TSearchRec;
  Identity, Device, Storage, Partition: TJSONObject;
  Partitions, Missing: TJSONArray;
  Number, Sectors, Value: Int64;
  BooleanValue: Boolean;
  Skip: Boolean;
begin
  Root := JoinPath(SysfsRoot, 'block');
  if not DirectoryExists(Root) then
    Exit;
  if FindFirst(JoinPath(Root, '*'), faAnyFile, Search) <> 0 then
    Exit;
  try
    repeat
      Name := Search.Name;
      if (Name = '.') or (Name = '..') then
        Continue;
      Skip := (Copy(Name, 1, 4) = 'loop') or (Copy(Name, 1, 3) = 'ram') or
        (Copy(Name, 1, 4) = 'zram') or (Copy(Name, 1, 3) = 'dm-') or
        (Copy(Name, 1, 2) = 'md') or (Copy(Name, 1, 2) = 'sr');
      if Skip then
        Continue;

      EntryPath := JoinPath(Root, Name);
      DevicePath := JoinPath(EntryPath, 'device');
      if not DirectoryExists(DevicePath) then
        Continue;

      Model := ReadValue(JoinPath(DevicePath, 'model'));
      if Model = '' then Model := Name;
      Vendor := ReadValue(JoinPath(DevicePath, 'vendor'));
      if Copy(Name, 1, 4) = 'nvme' then Bus := 'nvme'
      else if Copy(Name, 1, 3) = 'mmc' then Bus := 'mmc'
      else if Copy(Name, 1, 2) = 'sd' then Bus := 'scsi'
      else Bus := 'unknown';

      Identity := TJSONObject.Create;
      Identity.Add('model', Model);
      Identity.Add('local_path', '/block/' + Name);
      AddIfPresent(Identity, 'manufacturer', Vendor);
      Device := NewBaseDevice('block-' + Name, 'storage-device', Bus,
        'sysfs:/block/' + Name,
        'Block storage identity, driver binding and topology were read from sysfs; ' +
        'partition tables and filesystems are not read.',
        ObservedAt, NewDriverFacts(DevicePath));
      Device.Add('identity', Identity);

      Storage := TJSONObject.Create;
      Missing := TJSONArray.Create;
      if ReadInteger(JoinPath(EntryPath, 'size'), Sectors) then
        Storage.Add('capacity_bytes', Sectors * 512)
      else Missing.Add('capacity_bytes');

      if ReadInteger(JoinPath(EntryPath, 'queue/logical_block_size'), Value) and (Value > 0) then
        Storage.Add('logical_block_size', Value)
      else Missing.Add('logical_block_size');
      if ReadInteger(JoinPath(EntryPath, 'queue/physical_block_size'), Value) and (Value > 0) then
        Storage.Add('physical_block_size', Value)
      else Missing.Add('physical_block_size');

      if ReadBoolean(JoinPath(EntryPath, 'queue/rotational'), BooleanValue) then
        Storage.Add('rotational', BooleanValue)
      else Missing.Add('rotational');
      if ReadBoolean(JoinPath(EntryPath, 'removable'), BooleanValue) then
        Storage.Add('removable', BooleanValue)
      else Missing.Add('removable');
      if ReadBoolean(JoinPath(EntryPath, 'ro'), BooleanValue) then
        Storage.Add('read_only', BooleanValue)
      else Missing.Add('read_only');

      Transport := StorageTransport(Name, DevicePath);
      Storage.Add('transport', Transport);
      if Transport = 'unknown' then Missing.Add('transport');

      Partitions := TJSONArray.Create;
      if FindFirst(JoinPath(EntryPath, '*'), faAnyFile, PartitionSearch) = 0 then
      begin
        repeat
          if (PartitionSearch.Name = '.') or (PartitionSearch.Name = '..') then
            Continue;
          if not FileExists(JoinPath(JoinPath(EntryPath, PartitionSearch.Name), 'partition')) then
            Continue;
          Partition := TJSONObject.Create;
          Partition.Add('name', PartitionSearch.Name);
          if ReadInteger(JoinPath(JoinPath(EntryPath, PartitionSearch.Name), 'partition'), Number) then
            Partition.Add('number', Number);
          if ReadInteger(JoinPath(JoinPath(EntryPath, PartitionSearch.Name), 'start'), Number) then
            Partition.Add('start_sector', Number);
          if ReadInteger(JoinPath(JoinPath(EntryPath, PartitionSearch.Name), 'size'), Number) then
            Partition.Add('sectors', Number);
          Partitions.Add(Partition);
        until FindNext(PartitionSearch) <> 0;
        FindClose(PartitionSearch);
        Storage.Add('partitions', Partitions);
      end
      else
      begin
        Partitions.Free;
        Missing.Add('partitions');
      end;

      if Missing.Count > 0 then Storage.Add('unavailable', Missing)
      else Missing.Free;
      Device.Add('storage', Storage);
      Devices.Add(Device);
    until FindNext(Search) <> 0;
  finally
    FindClose(Search);
  end;
end;

procedure AddDisplayDevices(const SysfsRoot, ObservedAt: string; Devices: TJSONArray);
var
  Root, Name, EntryPath, Status, ModesText, Mode: string;
  Names: TStringList;
  Display, Device: TJSONObject;
  Modes: TJSONArray;
  Lines: TStringList;
  Index: Integer;
begin
  Root := JoinPath(SysfsRoot, 'class/drm');
  if not DirectoryExists(Root) then
    Exit;
  Names := TStringList.Create;
  try
    ListSortedEntries(Root, Names);
    for Index := 0 to Names.Count - 1 do
    begin
      Name := Names[Index];
      if Pos('-', Name) = 0 then
        Continue;
      EntryPath := JoinPath(Root, Name);
      if not FileExists(JoinPath(EntryPath, 'status')) then
        Continue;

      Display := TJSONObject.Create;
      Display.Add('connector', Name);
      Status := ReadValue(JoinPath(EntryPath, 'status'));
      if (Status = 'connected') or (Status = 'disconnected') then
        Display.Add('connected', Status = 'connected');

      ModesText := ReadFile(JoinPath(EntryPath, 'modes'), 65536);
      Modes := TJSONArray.Create;
      if ModesText <> '' then
      begin
        Lines := TStringList.Create;
        try
          Lines.Text := ModesText;
          for Index := 0 to Lines.Count - 1 do
            if Trim(Lines[Index]) <> '' then
              Modes.Add(Trim(Lines[Index]));
        finally
          Lines.Free;
        end;
      end;
      if Modes.Count > 0 then Display.Add('advertised_modes', Modes)
      else Modes.Free;
      Mode := ReadValue(JoinPath(EntryPath, 'mode'));
      AddIfPresent(Display, 'active_mode', Mode);

      Device := NewBaseDevice('display-' + Name, 'display', 'edid',
        'sysfs:/class/drm/' + Name,
        'DRM connector status and mode metadata were read from sysfs; no display function test was run.',
        ObservedAt, nil);
      Device.Add('display', Display);
      Devices.Add(Device);
    end;
  finally
    Names.Free;
  end;
end;

function CollectReport(const SysfsRoot, ProcRoot: string): TJSONObject;
var
  ObservedAt, Architecture, KernelRelease, BootMode, BootEvidence: string;
  Platform: TJSONObject;
  Environment, Collector, Privacy: TJSONObject;
  Collectors, Devices, Warnings, Limitations, Redactions: TJSONArray;
  Device: TJSONObject;
begin
  ObservedAt := CurrentTimestampUTC;
  Architecture := ArchitectureName;
  KernelRelease := ReadValue(JoinPath(ProcRoot, 'sys/kernel/osrelease'));
  if KernelRelease = '' then
    KernelRelease := 'unknown';
  Platform := CollectPlatform(SysfsRoot);
  BootMode := DetectBootMode(SysfsRoot, Architecture, BootEvidence);

  Environment := TJSONObject.Create;
  Environment.Add('architecture', Architecture);
  Environment.Add('kernel_release', KernelRelease);
  Environment.Add('boot_mode', BootMode);
  Environment.Add('boot_mode_evidence', BootEvidence);
  Environment.Add('virtualization', DetectVirtualization(SysfsRoot, Platform));
  if Platform.Count > 0 then
    Environment.Add('platform', Platform)
  else
    Platform.Free;

  Devices := TJSONArray.Create;
  Device := CollectCPU(ProcRoot, SysfsRoot, ObservedAt);
  if Device <> nil then Devices.Add(Device);
  Platform := CollectPlatform(SysfsRoot);
  Device := CollectBoard(Platform, ObservedAt);
  if Device <> nil then Devices.Add(Device);
  Platform.Free;

  AddPCIDevices(SysfsRoot, ObservedAt, Devices);
  AddUSBDevices(SysfsRoot, ObservedAt, Devices);
  AddBlockDevices(SysfsRoot, ObservedAt, Devices);
  AddDisplayDevices(SysfsRoot, ObservedAt, Devices);

  Collectors := TJSONArray.Create;
  Collector := TJSONObject.Create;
  Collector.Add('name', 'wsm-hwcheck-fpc-sysfs');
  Collector.Add('version', WSM_FPC_VERSION);
  Collector.Add('available', True);
  Collector.Add('scope', 'unprivileged-read-only');
  Collector.Add('notes',
    'Native Free Pascal collector; reads sysfs and procfs only. It does not execute external commands, access the network, load modules, update firmware, or write to target devices.');
  Collectors.Add(Collector);

  Warnings := TJSONArray.Create;
  if not DirectoryExists(JoinPath(SysfsRoot, 'bus/pci/devices')) then
    Warnings.Add('PCI sysfs inventory is unavailable; no PCI device claim is made.');
  if not FileExists(JoinPath(ProcRoot, 'cpuinfo')) then
    Warnings.Add('procfs:/cpuinfo is unavailable; CPU identity remains unknown.');

  Limitations := TJSONArray.Create;
  Limitations.Add('Runtime module availability and current-boot kernel-log firmware diagnostics are not implemented in this FPC revision.');
  Limitations.Add('PCI vendor/device names are not inferred from IDs; no external or network naming database is consulted.');
  Limitations.Add('USB composite interfaces, EDID decoding, and device-to-display topology are not collected.');
  Limitations.Add('Inventory is not a functional compatibility test; driver binding does not imply that a device works.');

  Privacy := TJSONObject.Create;
  Privacy.Add('profile', 'strict-local');
  Privacy.Add('network_upload_performed', False);
  Privacy.Add('sensitive_identifiers_included', False);
  { Python перелічує рівно ті сім редагувань, які справді застосовує
    (collector.py, redactions_applied). Порожній масив тут означав би інше
    твердження — «нічого не вирізано», а не «перелік не заповнено». }
  Redactions := TJSONArray.Create;
  Redactions.Add('serial-number');
  Redactions.Add('mac-address');
  Redactions.Add('uuid');
  Redactions.Add('hostname');
  Redactions.Add('username');
  Redactions.Add('ip-address');
  Redactions.Add('storage-wwn');
  Privacy.Add('redactions_applied', Redactions);
  Privacy.Add('network_requests_performed', False);

  Result := TJSONObject.Create;
  Result.Add('schema_version', WSM_SCHEMA_VERSION);
  Result.Add('report_id', NewReportId);
  Result.Add('collected_at', ObservedAt);
  Result.Add('environment', Environment);
  Result.Add('collectors', Collectors);
  Result.Add('devices', Devices);
  Result.Add('warnings', Warnings);
  Result.Add('limitations', Limitations);
  Result.Add('privacy', Privacy);
end;

end.
