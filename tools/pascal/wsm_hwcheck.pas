{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-hwcheck, FPC edition: read PCI identity from sysfs and emit the same
  report shape the Python collector emits.

  Why Pascal: the Python package dragged three interpreter builds into every
  consumer's closure (226 MB of a 399 MB store). A native binary needs no
  interpreter, no site-packages, no schema library — the JSON is written by
  hand, and the schema check happens in CI where Python already exists.

  Scope of this unit: devices only, read-only, no root, no writes. Anything
  that would touch a block device is deliberately absent.
}
program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix;

const
  PciDevices = '/sys/bus/pci/devices';
  SchemaVersion = '1.0.0';

type
  TDevice = record
    DeviceId: string;
    Category: string;
    Bus: string;
    VendorId: string;
    ProductId: string;
    SubsystemVendorId: string;
    SubsystemDeviceId: string;
    Driver: string;
    Source: string;
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
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #8:  Result := Result + '\b';
      #9:  Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
    else
      if C < #32 then
        Result := Result + Format('\u%.4x', [Ord(C)])
      else
        Result := Result + C;
    end;
  end;
end;

{ sysfs writes the class as 0xCCSShh; the report wants a category name. }
function CategoryOf(const ClassValue: string): string;
var
  Base: string;
begin
  Base := LowerCase(ClassValue);
  if Copy(Base, 1, 2) = '0x' then
    Base := Copy(Base, 3, Length(Base) - 2);
  if Copy(Base, 1, 2) = '03' then
    Result := 'display'
  else if Copy(Base, 1, 2) = '02' then
    Result := 'network'
  else if Copy(Base, 1, 2) = '01' then
    Result := 'storage'
  else if Copy(Base, 1, 2) = '04' then
    Result := 'multimedia'
  else if Copy(Base, 1, 2) = '0c' then
    Result := 'serial'
  else
    Result := 'other';
end;

{ Basename of a sysfs symlink, or '' when the link is absent.

  The RTL signature is fpReadLink(name, linkname: pchar; maxlen: size_t): cint —
  it fills a caller buffer and returns a length. There is no one-argument
  form returning a string, and FPC 3.2.2 does not convert AnsiString to PChar
  implicitly, so the first argument must be wrapped: the compiler proved both
  points with
    wsm_hwcheck.pas(89,45) Error: Incompatible type for arg no. 1:
    Got "AnsiString", expected "PChar"
}
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

function DriverOf(const DevicePath: string): string;
var
  Link: string;
begin
  { A bound device has a `driver' symlink; its basename is the module name. }
  Link := ReadLinkName(DevicePath + '/driver');
  if Link = '' then
    Result := ''
  else
    Result := ExtractFileName(Link);
end;

procedure EmitDevice(const DevicePath: string; var First: Boolean);
var
  D: TDevice;
  Name: string;
begin
  Name := ExtractFileName(DevicePath);
  D.DeviceId := 'pci-' + Name;
  D.Bus := 'pci';
  D.VendorId := ReadTrimmed(DevicePath + '/vendor');
  D.ProductId := ReadTrimmed(DevicePath + '/device');
  if (D.VendorId = '') and (D.ProductId = '') then
    Exit;
  D.SubsystemVendorId := ReadTrimmed(DevicePath + '/subsystem_vendor');
  D.SubsystemDeviceId := ReadTrimmed(DevicePath + '/subsystem_device');
  D.Category := CategoryOf(ReadTrimmed(DevicePath + '/class'));
  D.Driver := DriverOf(DevicePath);
  D.Source := 'sysfs:/bus/pci/devices/' + Name;

  if not First then
    Write(',');
  First := False;

  Write('{"device_id":"', JsonEscape(D.DeviceId), '"');
  Write(',"category":"', JsonEscape(D.Category), '"');
  Write(',"bus":"pci"');
  Write(',"discovery_status":"discovered"');
  Write(',"identity":{"vendor_id":"', JsonEscape(D.VendorId), '"');
  Write(',"device_id":"', JsonEscape(D.ProductId), '"');
  if D.SubsystemVendorId <> '' then
    Write(',"subsystem_vendor_id":"', JsonEscape(D.SubsystemVendorId), '"');
  if D.SubsystemDeviceId <> '' then
    Write(',"subsystem_device_id":"', JsonEscape(D.SubsystemDeviceId), '"');
  Write('}');
  { Словник статусів мусить бути той самий, що в Python-колекторі:
    bound / none-known / unknown. «unbound» не зустрічається ніде в Python,
    тому паритетний тест на ньому б падав — і правильно. }
  if D.Driver = '' then
    Write(',"driver":{"status":"none-known"}')
  else
    Write(',"driver":{"status":"bound","module":"', JsonEscape(D.Driver), '"}');
  { The Python collector emits these three as explicit unknowns; a native
    reader that invented values here would be worse than one that says so. }
  Write(',"firmware":{"status":"unknown"}');
  Write(',"functional_tests":[]');
  Write(',"evidence":[{"source":"', JsonEscape(D.Source),
        '","summary":"PCI identity and driver binding read from sysfs."}]');
  Write('}');
end;

var
  SearchRec: TSearchRec;
  First: Boolean;
  Found: Boolean;
  Count: Integer;
begin
  if ParamCount > 0 then
  begin
    WriteLn(StdErr, 'usage: wsm-hwcheck');
    Halt(2);
  end;

  if not DirectoryExists(PciDevices) then
  begin
    WriteLn(StdErr, 'wsm-hwcheck: no PCI bus at ', PciDevices);
    Halt(3);
  end;

  Write('{"schema_version":"', SchemaVersion, '"');
  Write(',"devices":[');

  First := True;
  Found := False;
  Count := 0;
  if FindFirst(PciDevices + '/*', faDirectory, SearchRec) = 0 then
  begin
    try
      repeat
        if (SearchRec.Name = '.') or (SearchRec.Name = '..') then
          Continue;
        if (SearchRec.Attr and faDirectory) = 0 then
          Continue;
        EmitDevice(PciDevices + '/' + SearchRec.Name, First);
        Inc(Count);
        Found := True;
      until FindNext(SearchRec) <> 0;
    finally
      FindClose(SearchRec);
    end;
  end;

  Write(']');
  { A report with no devices is a finding, not a success. }
  if not Found then
    Write(',"warnings":["no PCI devices were readable from sysfs"]');
  Write(',"limitations":["PCI identity only; USB, CPU and memory are not collected here"]');
  WriteLn('}');

  if not Found then
    Halt(4);
end.
