{ SPDX-License-Identifier: LicenseRef-Volnist }
{ WSM Desktop — native Free Pascal hardware collector, first verified slice. }
{
  This executable collects PCI function identity and current driver binding.
  It is deliberately not yet a replacement for the complete wsm_hwcheck
  report: CPU/DMI, USB, block, DRM connector, firmware and kernel-log evidence
  are separate parity tasks. Its JSON is a versioned diagnostic slice, not the
  hardware-report.schema.json document.

  All observations are read-only. No subprocess, network, MMIO, module load,
  firmware operation, privileged operation, disk write, or installer action
  is performed.

  Free Pascal 3.2.2 is pinned by .github/workflows/fpc-build.yml. The workflow
  must compile Pascal program declarations in .pas as well as .lpr/.pp files;
  the standalone program in this file uses the conventional .pas extension.

  --sysfs-root and --proc-root exist for deterministic fixture tests. They do
  not change the default /sys and /proc paths.
}

program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix, Unix;

const
  CollectorName = 'wsm-hwcheck-pascal';
  CollectorVersion = '0.1.0-dev';

var
  SysRoot: string = '/sys';
  ProcRoot: string = '/proc';

function WithTrailingDelimiter(const Value: string): string;
begin
  Result := IncludeTrailingPathDelimiter(Value);
end;

function ReadFirstLine(const Path: string): string;
var
  Stream: TFileStream;
  Buffer: array[0..4095] of Char;
  BytesRead: LongInt;
begin
  Result := '';
  try
    Stream := TFileStream.Create(Path, fmOpenRead or fmShareDenyNone);
  except
    Exit;
  end;

  try
    BytesRead := Stream.Read(Buffer, SizeOf(Buffer) - 1);
    if BytesRead > 0 then
    begin
      Buffer[BytesRead] := #0;
      Result := Trim(StrPas(@Buffer[0]));
    end;
  finally
    Stream.Free;
  end;
end;

function ReadDriverLink(const DevicePath: string): string;
var
  LinkTarget: array[0..1023] of Char;
  BytesRead: LongInt;
begin
  Result := '';
  FillChar(LinkTarget, SizeOf(LinkTarget), 0);
  BytesRead := fpReadLink(DevicePath + '/driver', @LinkTarget[0], SizeOf(LinkTarget) - 1);
  if (BytesRead <= 0) or (BytesRead >= SizeOf(LinkTarget)) then
    Exit;

  LinkTarget[BytesRead] := #0;
  Result := ExtractFileName(StrPas(@LinkTarget[0]));
end;

function ReadModuleLink(const DevicePath: string): string;
var
  LinkTarget: array[0..1023] of Char;
  BytesRead: LongInt;
begin
  Result := '';
  FillChar(LinkTarget, SizeOf(LinkTarget), 0);
  BytesRead := fpReadLink(DevicePath + '/driver/module', @LinkTarget[0], SizeOf(LinkTarget) - 1);
  if (BytesRead <= 0) or (BytesRead >= SizeOf(LinkTarget)) then
    Exit;

  LinkTarget[BytesRead] := #0;
  Result := ExtractFileName(StrPas(@LinkTarget[0]));
end;

function ReadMachineName: string;
var
  SystemInfo: UtsName;
begin
  Result := 'unknown';
  FillChar(SystemInfo, SizeOf(SystemInfo), 0);
  if fpUname(SystemInfo) = 0 then
    Result := StrPas(@SystemInfo.Machine[0]);
  if Result = '' then
    Result := 'unknown';
end;

function ReadKernelRelease: string;
var
  SystemInfo: UtsName;
begin
  Result := ReadFirstLine(WithTrailingDelimiter(ProcRoot) + 'sys/kernel/osrelease');
  if Result <> '' then
    Exit;

  Result := 'unknown';
  FillChar(SystemInfo, SizeOf(SystemInfo), 0);
  if fpUname(SystemInfo) = 0 then
    Result := StrPas(@SystemInfo.Release[0]);
  if Result = '' then
    Result := 'unknown';
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

procedure CollectPciAddresses(const Addresses: TStrings);
var
  Search: TSearchRec;
  Root, EntryPath: string;
begin
  Root := WithTrailingDelimiter(SysRoot) + 'bus/pci/devices';
  if FindFirst(WithTrailingDelimiter(Root) + '*', faAnyFile, Search) <> 0 then
    Exit;

  try
    repeat
      if (Search.Name = '.') or (Search.Name = '..') then
        Continue;

      EntryPath := WithTrailingDelimiter(Root) + Search.Name;
      { Sysfs exposes PCI functions as symlinks to device directories. }
      if DirectoryExists(EntryPath) then
        Addresses.Add(Search.Name);
    until FindNext(Search) <> 0;
  finally
    FindClose(Search);
  end;
end;

procedure EmitDriver(const DevicePath: string);
var
  DriverName, ModuleName: string;
begin
  DriverName := ReadDriverLink(DevicePath);
  ModuleName := ReadModuleLink(DevicePath);

  Write('      "driver": {');
  if DriverName = '' then
    Write('"status": "none-known"')
  else
  begin
    Write('"status": "bound", "bound_driver": "', JsonEscape(DriverName), '"');
    if ModuleName <> '' then
      Write(', "module": "', JsonEscape(ModuleName), '", "module_loaded": true');
  end;
  WriteLn('}');
end;

procedure EmitReport(const Addresses: TStrings);
var
  Index: Integer;
  Address, DevicePath, VendorId, DeviceId, ClassId: string;
  FirstDevice: Boolean;
begin
  WriteLn('{');
  WriteLn('  "collector": "', CollectorName, '",');
  WriteLn('  "collector_version": "', CollectorVersion, '",');
  WriteLn('  "environment": {');
  WriteLn('    "architecture": "', JsonEscape(ReadMachineName), '",');
  WriteLn('    "kernel_release": "', JsonEscape(ReadKernelRelease), '"');
  WriteLn('  },');
  WriteLn('  "pci": [');

  FirstDevice := True;
  for Index := 0 to Addresses.Count - 1 do
  begin
    Address := Addresses[Index];
    DevicePath := WithTrailingDelimiter(SysRoot) + 'bus/pci/devices/' + Address;
    VendorId := ReadFirstLine(DevicePath + '/vendor');
    DeviceId := ReadFirstLine(DevicePath + '/device');
    ClassId := ReadFirstLine(DevicePath + '/class');

    { Match the Python collector: ignore entries without vendor and device IDs. }
    if (VendorId = '') and (DeviceId = '') then
      Continue;

    if not FirstDevice then
      WriteLn(',');
    FirstDevice := False;

    WriteLn('    {');
    WriteLn('      "address": "', JsonEscape(Address), '",');
    WriteLn('      "vendor": "', JsonEscape(VendorId), '",');
    WriteLn('      "device": "', JsonEscape(DeviceId), '",');
    WriteLn('      "class": "', JsonEscape(ClassId), '",');
    EmitDriver(DevicePath);
    Write('    }');
  end;

  if not FirstDevice then
    WriteLn;
  WriteLn('  ],');
  WriteLn('  "evidence_level": "read-only sysfs and uname; no MMIO, module load, or disk write"');
  WriteLn('}');
end;

procedure ShowHelp;
begin
  WriteLn('wsm-hwcheck-pascal ', CollectorVersion);
  WriteLn('Read-only PCI identity and driver-binding evidence.');
  WriteLn('Usage: wsm_hwcheck [--sysfs-root PATH] [--proc-root PATH]');
  WriteLn('       wsm_hwcheck --help');
  WriteLn('       wsm_hwcheck --version');
  WriteLn('The default roots are /sys and /proc.');
end;

procedure ParseArguments;
var
  Index: Integer;
  Argument: string;
begin
  Index := 1;
  while Index <= ParamCount do
  begin
    Argument := ParamStr(Index);

    if (Argument = '--help') or (Argument = '-h') then
    begin
      ShowHelp;
      Halt(0);
    end;

    if Argument = '--version' then
    begin
      WriteLn(CollectorVersion);
      Halt(0);
    end;

    if (Argument = '--sysfs-root') or (Argument = '--proc-root') then
    begin
      if Index >= ParamCount then
      begin
        WriteLn(StdErr, 'wsm-hwcheck-pascal: missing value for ', Argument);
        Halt(2);
      end;

      Inc(Index);
      if (Argument = '--sysfs-root') then
        SysRoot := ExpandFileName(ParamStr(Index))
      else
        ProcRoot := ExpandFileName(ParamStr(Index));
    end
    else
    begin
      WriteLn(StdErr, 'wsm-hwcheck-pascal: unknown argument: ', Argument);
      Halt(2);
    end;

    Inc(Index);
  end;
end;

var
  PciAddresses: TStringList;
begin
  ParseArguments;

  PciAddresses := TStringList.Create;
  try
    PciAddresses.Sorted := True;
    PciAddresses.Duplicates := dupIgnore;
    CollectPciAddresses(PciAddresses);
    EmitReport(PciAddresses);
  finally
    PciAddresses.Free;
  end;
end.
