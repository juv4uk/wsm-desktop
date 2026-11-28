{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-hwcheck, FPC edition.

  This binary emits the hardware-report/1.1.0 envelope and a deliberately
  bounded PCI-function subset. It reads sysfs and uname only. Unknown firmware
  facts remain unknown; no device is certified and no system state is changed.
}
program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix, DateUtils, fpjson;

const
  PciDevices = '/sys/bus/pci/devices';
  DmiRoot = '/sys/class/dmi/id';
  SchemaVersion = '1.1.0';
  CollectorVersion = '0.1.0';

function ReadTrimmed(const Path: string): string;
var
  F: TextFile;
  Line: string;
begin
  Result := '';
  if not FileExists(Path) then
    Exit;
  AssignFile(F, Path);
  {$I-} Reset(F); {$I+}
  if IOResult <> 0 then
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

function JsonStringOrUnknown(const Value: string): string;
begin
  if Value = '' then
    Result := 'unknown'
  else
    Result := Value;
end;

function CleanDmi(const Value: string): string;
var
  LowerValue: string;
begin
  Result := Trim(Value);
  LowerValue := LowerCase(Result);
  if (LowerValue = 'to be filled by o.e.m.') or
     (LowerValue = 'to be filled by oem') or
     (LowerValue = 'default string') then
    Result := '';
end;

function CategoryOf(const ClassValue: string): string;
var
  Base: string;
begin
  Base := LowerCase(Trim(ClassValue));
  if Copy(Base, 1, 2) = '0x' then
    Base := Copy(Base, 3, Length(Base) - 2);
  if Copy(Base, 1, 2) = '03' then
    Result := 'gpu'
  else if Copy(Base, 1, 2) = '02' then
    Result := 'network'
  else if Copy(Base, 1, 2) = '04' then
    Result := 'audio'
  else if Copy(Base, 1, 2) = '01' then
    Result := 'storage-controller'
  else if Copy(Base, 1, 4) = '0c03' then
    Result := 'usb-controller'
  else
    Result := 'other';
end;

function ReadLinkName(const LinkPath: string): string;
var
  Buffer: array[0..1023] of Char;
  Count: SizeInt;
begin
  Result := '';
  FillChar(Buffer, SizeOf(Buffer), 0);
  Count := fpReadLink(PChar(LinkPath), @Buffer[0], SizeOf(Buffer) - 1);
  if Count <= 0 then
    Exit;
  Buffer[Count] := #0;
  Result := StrPas(@Buffer[0]);
end;

function DriverLink(const DevicePath, Suffix: string): string;
var
  Target: string;
begin
  Target := ReadLinkName(DevicePath + Suffix);
  if Target = '' then
    Result := ''
  else
    Result := ExtractFileName(ExcludeTrailingPathDelimiter(Target));
end;

function BuildDriver(const DevicePath: string): TJSONObject;
var
  BoundDriver, ModuleName: string;
begin
  Result := TJSONObject.Create;
  if not DirectoryExists(DevicePath) then
  begin
    Result.Add('status', 'unknown');
    Exit;
  end;

  BoundDriver := DriverLink(DevicePath, '/driver');
  if BoundDriver = '' then
  begin
    Result.Add('status', 'none-known');
    Result.Add('notes',
      'No driver symlink is present in sysfs for this device, so no driver was bound at collection time.');
    Exit;
  end;

  Result.Add('status', 'bound');
  Result.Add('bound_driver', BoundDriver);
  ModuleName := DriverLink(DevicePath, '/driver/module');
  if ModuleName <> '' then
  begin
    Result.Add('module', ModuleName);
    Result.Add('module_loaded', True);
  end;
end;

procedure AddOptionalFile(Target: TJSONObject; const JsonName, FileName: string);
var
  Value: string;
begin
  Value := ReadTrimmed(FileName);
  if Value <> '' then
    Target.Add(JsonName, Value);
end;

function BuildDevice(const DevicePath, ObservedAt: string): TJSONObject;
var
  Name, Vendor, Product, SourcePath, Category: string;
  Identity, Firmware, EvidenceItem, Driver: TJSONObject;
  Tests, Evidence, Recommendations: TJSONArray;
begin
  Result := nil;
  if not DirectoryExists(DevicePath) then
    Exit;

  Name := ExtractFileName(DevicePath);
  Vendor := ReadTrimmed(DevicePath + '/vendor');
  Product := ReadTrimmed(DevicePath + '/device');
  if (Vendor = '') and (Product = '') then
    Exit;

  SourcePath := 'sysfs:/bus/pci/devices/' + Name;
  Category := CategoryOf(ReadTrimmed(DevicePath + '/class'));

  Result := TJSONObject.Create;
  Result.Add('device_id', 'pci-' + Name);
  Result.Add('category', Category);
  Result.Add('bus', 'pci');
  Result.Add('discovery_status', 'discovered');

  Identity := TJSONObject.Create;
  Identity.Add('local_path', 'bus/pci/devices/' + Name);
  AddOptionalFile(Identity, 'vendor_id', DevicePath + '/vendor');
  AddOptionalFile(Identity, 'device_id', DevicePath + '/device');
  AddOptionalFile(Identity, 'subsystem_vendor_id', DevicePath + '/subsystem_vendor');
  AddOptionalFile(Identity, 'subsystem_device_id', DevicePath + '/subsystem_device');
  AddOptionalFile(Identity, 'revision', DevicePath + '/revision');
  AddOptionalFile(Identity, 'class_id', DevicePath + '/class');
  AddOptionalFile(Identity, 'modalias', DevicePath + '/modalias');
  Result.Add('identity', Identity);

  Driver := BuildDriver(DevicePath);
  Result.Add('driver', Driver);

  Firmware := TJSONObject.Create;
  Firmware.Add('requirement', 'unknown');
  Firmware.Add('runtime_status', 'unknown');
  Firmware.Add('redistribution_status', 'unknown');
  Result.Add('firmware', Firmware);

  Tests := TJSONArray.Create;
  Result.Add('functional_tests', Tests);

  Evidence := TJSONArray.Create;
  EvidenceItem := TJSONObject.Create;
  EvidenceItem.Add('kind', 'live-observation');
  EvidenceItem.Add('source', SourcePath);
  EvidenceItem.Add('observed_at', ObservedAt);
  EvidenceItem.Add('confidence', 'confirmed');
  EvidenceItem.Add('summary',
    'PCI function and its kernel driver binding were read from sysfs.');
  Evidence.Add(EvidenceItem);
  Result.Add('evidence', Evidence);

  Recommendations := TJSONArray.Create;
  Result.Add('recommendations', Recommendations);
end;

procedure SortDevices(Devices: TStringList);
begin
  Devices.Sort;
end;

function BootModeOf(const Architecture: string; out Evidence: string): string;
begin
  if DirectoryExists('/sys/firmware/efi') then
  begin
    Result := 'uefi';
    Evidence := 'sysfs:/firmware/efi is present: the kernel was booted through EFI.';
  end
  else if ((LowerCase(Architecture) = 'x86_64') or
           (LowerCase(Architecture) = 'i386') or
           (LowerCase(Architecture) = 'i486') or
           (LowerCase(Architecture) = 'i586') or
           (LowerCase(Architecture) = 'i686')) and
          DirectoryExists(DmiRoot) then
  begin
    Result := 'bios';
    Evidence := 'sysfs:/firmware/efi is absent while x86 DMI identity is present: the firmware handed the kernel over in legacy BIOS/CSM mode.';
  end
  else
  begin
    Result := 'unknown';
    Evidence := 'Neither sysfs:/firmware/efi nor an x86 DMI identity is available, so the boot mode is not determined.';
  end;
end;

function VirtualizationOf(const SystemVendor, ProductName, BoardName: string): string;
var
  Hypervisor, Combined: string;
begin
  Hypervisor := LowerCase(ReadTrimmed('/sys/hypervisor/type'));
  if Pos('kvm', Hypervisor) > 0 then
    Exit('kvm');
  if Pos('xen', Hypervisor) > 0 then
    Exit('xen');

  Combined := LowerCase(SystemVendor + ' ' + ProductName + ' ' + BoardName);
  if (Pos('qemu', Combined) > 0) or (Pos('kvm', Combined) > 0) then
    Result := 'qemu'
  else if Pos('vmware', Combined) > 0 then
    Result := 'vmware'
  else if (Pos('virtualbox', Combined) > 0) or (Pos('innotek', Combined) > 0) then
    Result := 'other'
  else if (Pos('virtual machine', Combined) > 0) and
          (Pos('microsoft', Combined) > 0) then
    Result := 'hyper-v'
  else if Pos('xen', Combined) > 0 then
    Result := 'xen'
  else
    Result := 'unknown';
end;

function BuildPlatform: TJSONObject;
var
  Value: string;
begin
  Result := TJSONObject.Create;
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/sys_vendor'));
  if Value <> '' then Result.Add('system_vendor', Value);
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/product_name'));
  if Value <> '' then Result.Add('product_name', Value);
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/board_vendor'));
  if Value <> '' then Result.Add('board_vendor', Value);
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/board_name'));
  if Value <> '' then Result.Add('board_name', Value);
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/board_version'));
  if Value <> '' then Result.Add('board_version', Value);
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/bios_vendor'));
  if Value <> '' then Result.Add('bios_vendor', Value);
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/bios_version'));
  if Value <> '' then Result.Add('bios_version', Value);
  Value := CleanDmi(ReadTrimmed(DmiRoot + '/bios_release'));
  if Value <> '' then Result.Add('bios_release', Value);
end;

function BuildReport(const Devices: TStringList; const Architecture,
  KernelRelease, ObservedAt, ReportId: string; const PciRootExists: Boolean): TJSONObject;
var
  Environment, Privacy, Collector, Platform: TJSONObject;
  Collectors, DeviceArray, Redactions, Limitations: TJSONArray;
  I: Integer;
  Device: TJSONObject;
  BootMode, BootEvidence, SystemVendor, ProductName, BoardName: string;
begin
  Result := TJSONObject.Create;
  Result.Add('schema_version', SchemaVersion);
  Result.Add('report_id', ReportId);
  Result.Add('collected_at', ObservedAt);

  Platform := BuildPlatform;
  SystemVendor := '';
  ProductName := '';
  BoardName := '';
  if Platform.Find('system_vendor') <> nil then
    SystemVendor := Platform.Get('system_vendor', '');
  if Platform.Find('product_name') <> nil then
    ProductName := Platform.Get('product_name', '');
  if Platform.Find('board_name') <> nil then
    BoardName := Platform.Get('board_name', '');

  Environment := TJSONObject.Create;
  Environment.Add('architecture', JsonStringOrUnknown(Architecture));
  Environment.Add('kernel_release', JsonStringOrUnknown(KernelRelease));
  BootMode := BootModeOf(Architecture, BootEvidence);
  Environment.Add('boot_mode', BootMode);
  Environment.Add('boot_mode_evidence', BootEvidence);
  Environment.Add('virtualization', VirtualizationOf(SystemVendor, ProductName, BoardName));
  if Platform.Count > 0 then
    Environment.Add('platform', Platform)
  else
    Platform.Free;
  Result.Add('environment', Environment);

  Collectors := TJSONArray.Create;
  Collector := TJSONObject.Create;
  Collector.Add('name', 'wsm-hwcheck-sysfs');
  Collector.Add('version', CollectorVersion);
  Collector.Add('available', True);
  Collector.Add('scope', 'unprivileged-read-only');
  Collector.Add('notes', 'Reads PCI identity and driver binding from sysfs and kernel identity from uname; no network or system mutations.');
  Collectors.Add(Collector);

  Collector := TJSONObject.Create;
  Collector.Add('name', 'wsm-pci-ids-database');
  Collector.Add('available', False);
  Collector.Add('scope', 'offline-database');
  Collector.Add('notes', 'The native FPC collector does not consult a pci.ids database; vendor and device identifiers remain raw sysfs values.');
  Collectors.Add(Collector);
  Result.Add('collectors', Collectors);

  DeviceArray := TJSONArray.Create;
  for I := 0 to Devices.Count - 1 do
  begin
    Device := BuildDevice(Devices[I], ObservedAt);
    if Device <> nil then
      DeviceArray.Add(Device);
  end;
  Result.Add('devices', DeviceArray);

  Privacy := TJSONObject.Create;
  Privacy.Add('profile', 'strict-local');
  Privacy.Add('network_upload_performed', False);
  Privacy.Add('sensitive_identifiers_included', False);
  Privacy.Add('network_requests_performed', False);
  Redactions := TJSONArray.Create;
  Privacy.Add('redactions_applied', Redactions);
  Result.Add('privacy', Privacy);

  if not PciRootExists then
  begin
    Limitations := TJSONArray.Create;
    Limitations.Add('The PCI sysfs root is unavailable; no PCI inventory was collected.');
    Result.Add('limitations', Limitations);
  end
  else
  begin
    Limitations := TJSONArray.Create;
    Limitations.Add('The FPC collector currently reads PCI functions only; CPU, USB, block storage and DRM are outside its scope.');
    Result.Add('limitations', Limitations);
  end;
end;

var
  SearchRec: TSearchRec;
  Devices: TStringList;
  SystemName: UtsName;
  Report: TJSONObject;
  Architecture, KernelRelease, ObservedAt, ReportId: string;
  Epoch: Int64;
  UtcDateTime: TDateTime;
  PciRootExists: Boolean;
  Found: Boolean;
  I: Integer;
begin
  Epoch := DateTimeToUnix(Now, False);
  UtcDateTime := UnixToDateTime(Epoch, True);
  ObservedAt := FormatDateTime('yyyy"-"mm"-"dd"T"hh":"nn":"ss"Z"', UtcDateTime);
  Randomize;
  ReportId := 'wsm-hwcheck-' + IntToStr(Epoch) + '-' + IntToStr(Random(1000000));

  FillChar(SystemName, SizeOf(SystemName), 0);
  Architecture := 'unknown';
  KernelRelease := 'unknown';
  if fpUname(SystemName) = 0 then
  begin
    Architecture := StrPas(@SystemName.Machine[0]);
    KernelRelease := StrPas(@SystemName.Release[0]);
  end;

  Devices := TStringList.Create;
  PciRootExists := DirectoryExists(PciDevices);
  Found := False;
  if PciRootExists and
     (FindFirst(PciDevices + '/*', faAnyFile or faSymLink, SearchRec) = 0) then
  begin
    try
      repeat
        if (SearchRec.Name = '.') or (SearchRec.Name = '..') then
          Continue;
        if (SearchRec.Attr and (faDirectory or faSymLink)) = 0 then
          Continue;
        if not DirectoryExists(PciDevices + '/' + SearchRec.Name) then
          Continue;
        Devices.Add(PciDevices + '/' + SearchRec.Name);
      until FindNext(SearchRec) <> 0;
    finally
      FindClose(SearchRec);
    end;
  end;
  SortDevices(Devices);

  for I := 0 to Devices.Count - 1 do
    if (ReadTrimmed(Devices[I] + '/vendor') <> '') or
       (ReadTrimmed(Devices[I] + '/device') <> '') then
    begin
      Found := True;
      Break;
    end;

  Report := BuildReport(Devices, Architecture, KernelRelease, ObservedAt,
    ReportId, PciRootExists);
  try
    WriteLn(Report.AsJSON);
  finally
    Report.Free;
    Devices.Free;
  end;

  if not PciRootExists then
  begin
    WriteLn(StdErr, 'wsm-hwcheck: no PCI bus at ' + PciDevices);
    Halt(3);
  end;

  { No readable PCI functions were found: emit a valid empty report and a diagnostic code. }
  if not Found then
  begin
    WriteLn(StdErr, 'wsm-hwcheck: No readable PCI functions were found');
    Halt(4);
  end;
end.
