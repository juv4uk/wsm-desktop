{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-hwcheck — FPC-native, read-only PCI inventory producer.

  This is an intentionally bounded first slice of the WSM hardware collector:
  it reads PCI identity and driver binding from sysfs and emits a valid
  wsm-hardware-report 1.1.0 document. It does not probe hardware, load modules,
  access MMIO, read block contents, run commands, access the network, or write
  files. It reports unknown firmware facts as unknown, never as success.

  Build: make -C tools/pascal
  Test:  python3 -m unittest tests.test_fpc_runtime
}
program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix, DateUtils;

const
  ToolVersion = '0.2.0';
  SchemaVersion = '1.1.0';

type
  TPciDevice = record
    Address: string;
    VendorId: string;
    DeviceId: string;
    SubsystemVendorId: string;
    SubsystemDeviceId: string;
    Revision: string;
    ClassId: string;
    Category: string;
    BoundDriver: string;
  end;
  TPciDevices = array of TPciDevice;

var
  SysfsRoot: string = '/sys';
  ProcRoot: string = '/proc';

function JoinPath(const Root, Relative: string): string;
begin
  Result := IncludeTrailingPathDelimiter(Root) + Relative;
end;

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

function JsonEscape(const Value: string): string;
var
  I: Integer;
  C: Char;
begin
  Result := '';
  for I := 1 to Length(Value) do
  begin
    C := Value[I];
    case C of
      '"': Result := Result + '\' + '"';
      '\': Result := Result + '\\';
      #8:  Result := Result + '\b';
      #9:  Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
    else
      if C < #32 then
        Result := Result + '\u' + IntToHex(Ord(C), 4)
      else
        Result := Result + C;
    end;
  end;
end;

function JsonString(const Value: string): string;
begin
  Result := '"' + JsonEscape(Value) + '"';
end;

function NormaliseHexId(const Value: string): string;
begin
  Result := LowerCase(Trim(Value));
  if Copy(Result, 1, 2) = '0x' then
    Delete(Result, 1, 2);
end;

function HostArchitecture: string;
begin
  {$IFDEF CPUX86_64}
  Result := 'x86_64';
  {$ELSE}
    {$IFDEF CPUI386}
    Result := 'i386';
    {$ELSE}
      {$IFDEF CPUAARCH64}
      Result := 'aarch64';
      {$ELSE}
        {$IFDEF CPUARM}
        Result := 'arm';
        {$ELSE}
          {$IFDEF CPURISCV64}
          Result := 'riscv64';
          {$ELSE}
          Result := 'unknown';
          {$ENDIF}
        {$ENDIF}
      {$ENDIF}
    {$ENDIF}
  {$ENDIF}
end;

function IsX86Architecture(const Architecture: string): Boolean;
var
  Value: string;
begin
  Value := LowerCase(Architecture);
  Result := (Value = 'x86_64') or (Value = 'amd64') or
    (Value = 'i386') or (Value = 'i486') or
    (Value = 'i586') or (Value = 'i686') or (Value = 'x86');
end;

function BootMode: string;
begin
  if DirectoryExists(JoinPath(SysfsRoot, 'firmware/efi')) then
    Exit('uefi');
  if IsX86Architecture(HostArchitecture) and
     DirectoryExists(JoinPath(SysfsRoot, 'class/dmi/id')) then
    Exit('bios');
  Result := 'unknown';
end;

function Virtualization: string;
var
  Value: string;
begin
  Value := LowerCase(ReadTrimmed(JoinPath(SysfsRoot, 'hypervisor/type')));
  if Pos('kvm', Value) > 0 then
    Result := 'kvm'
  else if Pos('xen', Value) > 0 then
    Result := 'xen'
  else if Value <> '' then
    Result := 'other'
  else
    Result := 'unknown';
end;

function CollectedAt: string;
begin
  Result := FormatDateTime(
    'yyyy"-"mm"-"dd"T"hh":"nn":"ss"Z"',
    LocalTimeToUniversal(Now)
  );
end;

function NewReportId: string;
begin
  Result := 'hwcheck-fpc-' +
    FormatDateTime('yyyymmddhhnnsszzz', LocalTimeToUniversal(Now)) +
    '-' + IntToStr(fpGetPid);
end;

function CategoryOf(const ClassValue: string): string;
var
  Base: string;
begin
  Base := NormaliseHexId(ClassValue);
  if Copy(Base, 1, 2) = '03' then
    Result := 'gpu'
  else if Copy(Base, 1, 2) = '02' then
    Result := 'network'
  else if Copy(Base, 1, 2) = '01' then
    Result := 'storage-controller'
  else if Copy(Base, 1, 2) = '04' then
    Result := 'audio'
  else if Copy(Base, 1, 4) = '0c03' then
    Result := 'usb-controller'
  else
    Result := 'other';
end;

function BoundDriverOf(const DevicePath: string): string;
var
  LinkTarget: RawByteString;
begin
  LinkTarget := fpReadLink(DevicePath + '/driver');
  if LinkTarget = '' then
    Result := ''
  else
    Result := ExtractFileName(String(LinkTarget));
end;

procedure CollectPciDevices(out Devices: TPciDevices; out Unreadable: Integer);
var
  Search: TSearchRec;
  PciRoot, DevicePath, Vendor, Product: string;
  D: TPciDevice;
begin
  SetLength(Devices, 0);
  Unreadable := 0;
  PciRoot := JoinPath(SysfsRoot, 'bus/pci/devices');
  if FindFirst(PciRoot + '/*', faAnyFile, Search) <> 0 then
    Exit;
  try
    repeat
      if (Search.Name = '.') or (Search.Name = '..') then
        Continue;
      DevicePath := JoinPath(PciRoot, Search.Name);
      Vendor := ReadTrimmed(DevicePath + '/vendor');
      Product := ReadTrimmed(DevicePath + '/device');
      if (Vendor = '') or (Product = '') then
      begin
        Inc(Unreadable);
        Continue;
      end;

      D.Address := Search.Name;
      D.VendorId := NormaliseHexId(Vendor);
      D.DeviceId := NormaliseHexId(Product);
      D.SubsystemVendorId := NormaliseHexId(
        ReadTrimmed(DevicePath + '/subsystem_vendor'));
      D.SubsystemDeviceId := NormaliseHexId(
        ReadTrimmed(DevicePath + '/subsystem_device'));
      D.Revision := ReadTrimmed(DevicePath + '/revision');
      D.ClassId := NormaliseHexId(ReadTrimmed(DevicePath + '/class'));
      D.Category := CategoryOf(D.ClassId);
      D.BoundDriver := BoundDriverOf(DevicePath);

      SetLength(Devices, Length(Devices) + 1);
      Devices[High(Devices)] := D;
    until FindNext(Search) <> 0;
  finally
    FindClose(Search);
  end;
end;

procedure EmitDevice(const D: TPciDevice; const ObservedAt: string);
var
  Source: string;
begin
  Source := 'sysfs:/bus/pci/devices/' + D.Address;
  Write('{"device_id":', JsonString('pci-' + D.Address));
  Write(',"category":', JsonString(D.Category));
  Write(',"bus":"pci","discovery_status":"discovered"');
  Write(',"identity":{"vendor_id":', JsonString(D.VendorId));
  Write(',"device_id":', JsonString(D.DeviceId));
  if D.SubsystemVendorId <> '' then
    Write(',"subsystem_vendor_id":', JsonString(D.SubsystemVendorId));
  if D.SubsystemDeviceId <> '' then
    Write(',"subsystem_device_id":', JsonString(D.SubsystemDeviceId));
  if D.Revision <> '' then
    Write(',"revision":', JsonString(D.Revision));
  if D.ClassId <> '' then
    Write(',"class_id":', JsonString(D.ClassId));
  Write('}');

  if D.BoundDriver = '' then
    Write(',"driver":{"status":"none-known","notes":"No driver symlink was present in sysfs."}')
  else
    Write(',"driver":{"status":"bound","bound_driver":',
      JsonString(D.BoundDriver), '}');

  Write(',"firmware":{"requirement":"unknown","runtime_status":"unknown","redistribution_status":"unknown"}');
  Write(',"functional_tests":[]');
  Write(',"evidence":[{"kind":"live-observation","source":',
    JsonString(Source), ',"observed_at":', JsonString(ObservedAt),
    ',"confidence":"confirmed","summary":"PCI identity and driver binding were read from sysfs."}]');
  Write(',"recommendations":[]}');
end;

procedure EmitReport(const Devices: TPciDevices; const Unreadable: Integer);
var
  I: Integer;
  Architecture, KernelRelease, Timestamp: string;
begin
  Architecture := HostArchitecture;
  KernelRelease := ReadTrimmed(JoinPath(ProcRoot, 'sys/kernel/osrelease'));
  if KernelRelease = '' then
    KernelRelease := 'unknown';
  Timestamp := CollectedAt;

  Write('{"schema_version":', JsonString(SchemaVersion));
  Write(',"report_id":', JsonString(NewReportId));
  Write(',"collected_at":', JsonString(Timestamp));
  Write(',"environment":{"architecture":', JsonString(Architecture));
  Write(',"kernel_release":', JsonString(KernelRelease));
  Write(',"boot_mode":', JsonString(BootMode));
  Write(',"virtualization":', JsonString(Virtualization), '}');

  Write(',"collectors":[{"name":"wsm-hwcheck-fpc","version":',
    JsonString(ToolVersion), ',"available":true');
  Write(',"scope":"unprivileged-read-only"');
  Write(',"notes":"PCI sysfs inventory only."}]');

  Write(',"devices":[');
  for I := 0 to High(Devices) do
  begin
    if I > 0 then
      Write(',');
    EmitDevice(Devices[I], Timestamp);
  end;
  Write(']');

  if (Length(Devices) = 0) or (Unreadable > 0) then
  begin
    Write(',"warnings":[');
    if Length(Devices) = 0 then
      Write('"No readable PCI devices were found under sysfs."');
    if (Length(Devices) = 0) and (Unreadable > 0) then
      Write(',');
    if Unreadable > 0 then
      Write(JsonString(IntToStr(Unreadable) +
        ' PCI sysfs entries did not expose readable vendor and device IDs.'));
    Write(']');
  end;

  Write(',"limitations":["PCI identity only; USB, CPU, memory, firmware requirements and runtime diagnostics are not collected by this first FPC slice."]');
  Write(',"privacy":{"profile":"strict-local","network_upload_performed":false');
  Write(',"sensitive_identifiers_included":false,"network_requests_performed":false}');
  WriteLn('}');
end;

procedure ParseArguments;
var
  I: Integer;
  Argument: string;
begin
  I := 1;
  while I <= ParamCount do
  begin
    Argument := ParamStr(I);
    if (Argument = '--help') or (Argument = '-h') then
    begin
      WriteLn('wsm-hwcheck-fpc ', ToolVersion);
      WriteLn('Read-only PCI identity collector; JSON is written to stdout.');
      WriteLn('Usage: wsm-hwcheck [--sysfs-root PATH] [--proc-root PATH]');
      Halt(0);
    end
    else if Argument = '--version' then
    begin
      WriteLn('wsm-hwcheck-fpc ', ToolVersion);
      Halt(0);
    end
    else if (Argument = '--sysfs-root') or (Argument = '--proc-root') then
    begin
      if I = ParamCount then
      begin
        WriteLn(StdErr, 'wsm-hwcheck: missing path after ', Argument);
        Halt(2);
      end;
      Inc(I);
      if Argument = '--sysfs-root' then
        SysfsRoot := ExcludeTrailingPathDelimiter(ParamStr(I))
      else
        ProcRoot := ExcludeTrailingPathDelimiter(ParamStr(I));
    end
    else
    begin
      WriteLn(StdErr, 'wsm-hwcheck: unknown argument: ', Argument);
      Halt(2);
    end;
    Inc(I);
  end;
end;

var
  Devices: TPciDevices;
  Unreadable: Integer;
  PciRoot: string;
begin
  ParseArguments;
  PciRoot := JoinPath(SysfsRoot, 'bus/pci/devices');
  if not DirectoryExists(PciRoot) then
  begin
    WriteLn(StdErr, 'wsm-hwcheck: PCI sysfs path is unavailable: ', PciRoot);
    Halt(3);
  end;

  CollectPciDevices(Devices, Unreadable);
  EmitReport(Devices, Unreadable);
  if (Length(Devices) = 0) then
    Halt(4);
end.
