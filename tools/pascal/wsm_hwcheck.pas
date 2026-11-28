{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-hwcheck, FPC edition.

  This native collector currently covers PCI identity and direct driver binding.
  It emits the complete WSM Hardware Evidence Report v1.1.0 envelope, while
  explicitly leaving non-PCI subsystems and runtime firmware diagnostics
  uncollected. Unknown is represented as unknown; it is never guessed.

  Read-only sources: uname(2), /sys/bus/pci/devices, /sys/firmware/efi,
  /sys/hypervisor/type and DMI sysfs. No shell, network, MMIO, module load,
  block-device access or writes.
}

program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix, DateUtils, fpjson;

const
  SysRoot = '/sys';
  PciDevices = '/sys/bus/pci/devices';
  SchemaVersion = '1.1.0';

type
  TDevice = record
    Address: string;
    VendorId: string;
    ProductId: string;
    SubsystemVendorId: string;
    SubsystemDeviceId: string;
    Revision: string;
    ClassId: string;
    ModAlias: string;
    Driver: string;
    ModuleName: string;
  end;

  TDeviceArray = array of TDevice;

function ReadTrimmed(const Path: string): string;
var
  F: TextFile;
  Line: string;
  ErrorCode: Integer;
begin
  Result := '';
  AssignFile(F, Path);
  {$I-} Reset(F); {$I+}
  ErrorCode := IOResult;
  if ErrorCode <> 0 then
    Exit;
  try
    if not Eof(F) then
    begin
      ReadLn(F, Line);
      Result := Trim(Line);
    end;
  finally
    CloseFile(F);
  end;
end;

function IsX86Machine(const Architecture: string): Boolean;
var
  Value: string;
begin
  Value := LowerCase(Architecture);
  Result := (Value = 'x86_64') or (Value = 'i386') or
            (Value = 'i486') or (Value = 'i586') or
            (Value = 'i686');
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

procedure ReadBootMode(const Architecture: string;
  out BootMode, BootEvidence: string);
begin
  if DirectoryExists(SysRoot + '/firmware/efi') then
  begin
    BootMode := 'uefi';
    BootEvidence := 'sysfs:/firmware/efi is present: the kernel was booted through EFI.';
    Exit;
  end;

  if IsX86Machine(Architecture) and DirectoryExists(SysRoot + '/class/dmi/id') then
  begin
    BootMode := 'bios';
    BootEvidence := 'sysfs:/firmware/efi is absent while an x86 DMI identity is present: the firmware handed the kernel over in legacy BIOS/CSM mode.';
    Exit;
  end;

  BootMode := 'unknown';
  BootEvidence := 'Neither sysfs:/firmware/efi nor an x86 DMI identity is available, so the boot mode is not determined.';
end;

function ReadPlatformFacts: TJSONObject;
var
  DmiRoot: string;
  Value: string;
begin
  Result := TJSONObject.Create;
  DmiRoot := SysRoot + '/class/dmi/id';

  Value := ReadTrimmed(DmiRoot + '/sys_vendor');
  if (Value <> '') and (LowerCase(Value) <> 'to be filled by o.e.m.') then
    Result.Add('system_vendor', Value);

  Value := ReadTrimmed(DmiRoot + '/product_name');
  if (Value <> '') and (LowerCase(Value) <> 'default string') then
    Result.Add('product_name', Value);

  Value := ReadTrimmed(DmiRoot + '/board_vendor');
  if Value <> '' then
    Result.Add('board_vendor', Value);

  Value := ReadTrimmed(DmiRoot + '/board_name');
  if Value <> '' then
    Result.Add('board_name', Value);

  Value := ReadTrimmed(DmiRoot + '/board_version');
  if Value <> '' then
    Result.Add('board_version', Value);

  Value := ReadTrimmed(DmiRoot + '/bios_vendor');
  if Value <> '' then
    Result.Add('bios_vendor', Value);

  Value := ReadTrimmed(DmiRoot + '/bios_version');
  if Value <> '' then
    Result.Add('bios_version', Value);

  Value := ReadTrimmed(DmiRoot + '/bios_release');
  if Value <> '' then
    Result.Add('bios_release', Value);
end;

function VirtualizationKind(const Platform: TJSONObject): string;
var
  Hypervisor, Combined: string;
begin
  Hypervisor := LowerCase(ReadTrimmed(SysRoot + '/hypervisor/type'));
  if Pos('kvm', Hypervisor) > 0 then
    Exit('kvm');
  if Pos('xen', Hypervisor) > 0 then
    Exit('xen');

  Combined := '';
  if Platform.IndexOfName('system_vendor') >= 0 then
    Combined := Combined + ' ' + Platform.Get('system_vendor', '');
  if Platform.IndexOfName('product_name') >= 0 then
    Combined := Combined + ' ' + Platform.Get('product_name', '');
  if Platform.IndexOfName('board_name') >= 0 then
    Combined := Combined + ' ' + Platform.Get('board_name', '');
  Combined := LowerCase(Combined);

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

function PciCategory(const ClassId: string): string;
var
  Value: string;
begin
  Value := LowerCase(ClassId);
  if Copy(Value, 1, 2) = '0x' then
    Delete(Value, 1, 2);

  if Copy(Value, 1, 2) = '03' then
    Result := 'gpu'
  else if Copy(Value, 1, 2) = '02' then
    Result := 'network'
  else if Copy(Value, 1, 2) = '04' then
    Result := 'audio'
  else if Copy(Value, 1, 2) = '01' then
    Result := 'storage-controller'
  else if Copy(Value, 1, 4) = '0c03' then
    Result := 'usb-controller'
  else
    Result := 'other';
end;

function DriverLink(const DevicePath, LinkName: string): string;
var
  LinkTarget: string;
begin
  Result := '';
  LinkTarget := fpReadLink(DevicePath + LinkName);
  if LinkTarget <> '' then
    Result := ExtractFileName(LinkTarget);
end;

procedure SortDevices(var Devices: TDeviceArray);
var
  I, J: Integer;
  Current: TDevice;
begin
  { sysfs enumeration order is not an API; use the same stable BDF order as Python. }
  for I := 1 to High(Devices) do
  begin
    Current := Devices[I];
    J := I - 1;
    while (J >= 0) and (CompareStr(Devices[J].Address, Current.Address) > 0) do
    begin
      Devices[J + 1] := Devices[J];
      Dec(J);
    end;
    Devices[J + 1] := Current;
  end;
end;

procedure CollectPci(var Devices: TDeviceArray);
var
  Search: TSearchRec;
  DevicePath: string;
  Item: TDevice;
  Index: Integer;
begin
  SetLength(Devices, 0);
  if FindFirst(PciDevices + '/*', faAnyFile or faSymLink, Search) <> 0 then
    Exit;
  try
    repeat
      if (Search.Name = '.') or (Search.Name = '..') then
        Continue;
      DevicePath := PciDevices + '/' + Search.Name;
      { PCI device entries are commonly symlinks to directories in sysfs. }
      if not DirectoryExists(DevicePath) then
        Continue;

      Item.Address := Search.Name;
      Item.VendorId := ReadTrimmed(DevicePath + '/vendor');
      Item.ProductId := ReadTrimmed(DevicePath + '/device');
      if (Item.VendorId = '') and (Item.ProductId = '') then
        Continue;

      Item.SubsystemVendorId := ReadTrimmed(DevicePath + '/subsystem_vendor');
      Item.SubsystemDeviceId := ReadTrimmed(DevicePath + '/subsystem_device');
      Item.Revision := ReadTrimmed(DevicePath + '/revision');
      Item.ClassId := ReadTrimmed(DevicePath + '/class');
      Item.ModAlias := ReadTrimmed(DevicePath + '/modalias');
      Item.Driver := DriverLink(DevicePath, '/driver');
      Item.ModuleName := DriverLink(DevicePath, '/driver/module');

      Index := Length(Devices);
      SetLength(Devices, Index + 1);
      Devices[Index] := Item;
    until FindNext(Search) <> 0;
  finally
    FindClose(Search);
  end;
  SortDevices(Devices);
end;

function UnknownFirmware: TJSONObject;
begin
  Result := TJSONObject.Create;
  Result.Add('requirement', 'unknown');
  Result.Add('runtime_status', 'unknown');
  Result.Add('redistribution_status', 'unknown');
end;

function BuildDevice(const Item: TDevice; const ObservedAt: string): TJSONObject;
var
  Identity, Driver, Evidence, EvidenceItem: TJSONObject;
  EvidenceArray: TJSONArray;
  DeviceId, Source, Summary: string;
begin
  Result := TJSONObject.Create;
  DeviceId := 'pci-' + Item.Address;
  Source := 'sysfs:/bus/pci/devices/' + Item.Address;
  Summary := 'PCI identity and direct driver binding were read from sysfs.';

  Result.Add('device_id', DeviceId);
  Result.Add('category', PciCategory(Item.ClassId));
  Result.Add('bus', 'pci');
  Result.Add('discovery_status', 'discovered');

  Identity := TJSONObject.Create;
  if Item.VendorId <> '' then Identity.Add('vendor_id', Item.VendorId);
  if Item.ProductId <> '' then Identity.Add('device_id', Item.ProductId);
  if Item.SubsystemVendorId <> '' then Identity.Add('subsystem_vendor_id', Item.SubsystemVendorId);
  if Item.SubsystemDeviceId <> '' then Identity.Add('subsystem_device_id', Item.SubsystemDeviceId);
  if Item.Revision <> '' then Identity.Add('revision', Item.Revision);
  if Item.ClassId <> '' then Identity.Add('class_id', Item.ClassId);
  if Item.ModAlias <> '' then Identity.Add('modalias', Item.ModAlias);
  Identity.Add('local_path', '/' + Source.Substring(5));
  Result.Add('identity', Identity);

  Driver := TJSONObject.Create;
  if Item.Driver = '' then
  begin
    Driver.Add('status', 'none-known');
    Driver.Add('notes', 'No driver symlink is present in sysfs for this device, so no driver was bound at collection time.');
  end
  else
  begin
    Driver.Add('status', 'bound');
    Driver.Add('bound_driver', Item.Driver);
    if Item.ModuleName <> '' then
    begin
      Driver.Add('module', Item.ModuleName);
      Driver.Add('module_loaded', True);
    end;
  end;
  Result.Add('driver', Driver);
  Result.Add('firmware', UnknownFirmware);
  Result.Add('functional_tests', TJSONArray.Create);

  EvidenceArray := TJSONArray.Create;
  EvidenceItem := TJSONObject.Create;
  EvidenceItem.Add('kind', 'live-observation');
  EvidenceItem.Add('source', Source);
  EvidenceItem.Add('observed_at', ObservedAt);
  EvidenceItem.Add('confidence', 'confirmed');
  EvidenceItem.Add('summary', Summary);
  EvidenceArray.Add(EvidenceItem);
  Result.Add('evidence', EvidenceArray);
  Result.Add('recommendations', TJSONArray.Create);
end;

function BuildReport(const Devices: TDeviceArray; const HasPciBus: Boolean): TJSONObject;
var
  Epoch: Int64;
  ObservedAt, Architecture, KernelRelease, BootMode, BootEvidence: string;
  Environment, Platform, Collectors, Collector, DeviceJson: TJSONObject;
  DeviceArray, Warnings, Limitations, Redactions: TJSONArray;
  Privacy: TJSONObject;
  I: Integer;
begin
  Epoch := fpTime;
  if Epoch < 0 then
    Epoch := 0;
  ObservedAt := DateTimeToISO8601(UnixToDateTime(Epoch, True), True);
  ReadSystemIdentity(Architecture, KernelRelease);
  ReadBootMode(Architecture, BootMode, BootEvidence);

  Result := TJSONObject.Create;
  Result.Add('schema_version', SchemaVersion);
  Result.Add('report_id', 'wsm-' + IntToStr(Epoch) + '-' + IntToStr(GetTickCount64 mod 1000000));
  Result.Add('collected_at', ObservedAt);

  Environment := TJSONObject.Create;
  Environment.Add('architecture', Architecture);
  Environment.Add('kernel_release', KernelRelease);
  Environment.Add('boot_mode', BootMode);
  Environment.Add('boot_mode_evidence', BootEvidence);
  Environment.Add('virtualization', 'unknown');
  Platform := ReadPlatformFacts;
  if Platform.Count > 0 then
  begin
    Environment.Add('platform', Platform);
    Environment.Strings['virtualization'] := VirtualizationKind(Platform);
  end;
  Result.Add('environment', Environment);

  Collectors := TJSONArray.Create;
  Collector := TJSONObject.Create;
  Collector.Add('name', 'wsm-hwcheck-sysfs');
  Collector.Add('version', '0.1.0');
  Collector.Add('available', True);
  Collector.Add('scope', 'unprivileged-read-only');
  Collector.Add('notes', 'Native Free Pascal collector. Reads uname and PCI sysfs only; no network requests or system mutations.');
  Collectors.Add(Collector);
  Result.Add('collectors', Collectors);

  DeviceArray := TJSONArray.Create;
  for I := 0 to High(Devices) do
  begin
    DeviceJson := BuildDevice(Devices[I], ObservedAt);
    DeviceArray.Add(DeviceJson);
  end;
  Result.Add('devices', DeviceArray);

  Warnings := TJSONArray.Create;
  if not HasPciBus then
    Warnings.Add('The PCI sysfs directory is unavailable; PCI inventory was not collected.')
  else if Length(Devices) = 0 then
    Warnings.Add('No readable PCI functions were found in sysfs.');
  Result.Add('warnings', Warnings);

  Limitations := TJSONArray.Create;
  Limitations.Add('This FPC collector reads PCI identity and direct driver binding only; CPU, USB, block, DRM, firmware-log and runtime diagnostics are not collected.');
  Limitations.Add('A driver binding is not proof that the device works; firmware state and functional tests remain unknown or not run.');
  Result.Add('limitations', Limitations);

  Privacy := TJSONObject.Create;
  Privacy.Add('profile', 'strict-local');
  Privacy.Add('network_upload_performed', False);
  Privacy.Add('network_requests_performed', False);
  Privacy.Add('sensitive_identifiers_included', False);
  Redactions := TJSONArray.Create;
  Redactions.Add('serial-number');
  Redactions.Add('mac-address');
  Redactions.Add('uuid');
  Redactions.Add('hostname');
  Redactions.Add('username');
  Redactions.Add('ip-address');
  Redactions.Add('storage-wwn');
  Privacy.Add('redactions_applied', Redactions);
  Result.Add('privacy', Privacy);
end;

var
  Devices: TDeviceArray;
  Report: TJSONObject;
  HasPciBus: Boolean;
  Argument: string;
begin
  if ParamCount > 0 then
  begin
    if (ParamCount = 1) and ((ParamStr(1) = '--help') or (ParamStr(1) = '-h')) then
    begin
      WriteLn('wsm-hwcheck — read-only PCI identity and driver evidence');
      WriteLn('usage: wsm-hwcheck');
      Halt(0);
    end;
    WriteLn(StdErr, 'wsm-hwcheck: unknown argument');
    Halt(2);
  end;

  HasPciBus := DirectoryExists(PciDevices);
  CollectPci(Devices);
  Report := BuildReport(Devices, HasPciBus);
  try
    WriteLn(Report.AsJSON);
  finally
    Report.Free;
  end;

  if (not HasPciBus) then
    Halt(3);
  if Length(Devices) = 0 then
    Halt(4);
end.
