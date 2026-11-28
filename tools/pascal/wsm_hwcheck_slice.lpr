{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-hwcheck-slice, FPC edition: the first vertical slice of the WSM hardware
  collector, and the command-line front end that the Python collector has.

  Scope is exactly three fact groups, the ones the H170 profile depends on:
    1. boot mode    - sysfs:/firmware/efi plus x86 DMI identity;
    2. GPU record   - PCI ids, driver binding, boot_vga, DRM card nodes and the
                      PCIe link, for every PCI function of class 03;
    3. BIOS         - sysfs:/class/dmi/id/bios_release and bios_date.
  Every fact no readable source provided goes into an `unavailable` array; it is
  never replaced by a default.

  Everything else in wsm_hwcheck/collector.py (CPU, USB, block devices, DRM
  connectors, runtime diagnostics, the pci.ids naming database) is deliberately
  not ported. The Python collector stays the shipped implementation until
  scripts/check_fpc_parity.py reports agreement on the synthetic fixtures.

  Read-only: this program opens files for reading, and writes only to the path
  named by --output. No socket, no child process, no block device.

  Single file on purpose: .github/workflows/fpc-build.yml compiles every tracked
  *.lpr with no -Fu unit search path, so a unit in a sibling file would not be
  found there. tools/pascal/wsm_hwcheck.pas and wsm_classify.pas are the same
  shape for the same reason.
}
program wsm_hwcheck_slice;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix;

const
  ProgName = 'wsm-hwcheck-slice';
  ToolVersion = '0.1.0-fpc-slice.1';
  SchemaVersion = '1.1.0';
  { A sysfs attribute is a page at most; a larger file is not one we want. }
  ReadLimit = 65536;
  NoDriverNotes =
    'No driver symlink is present in sysfs for this device, so no driver was bound at collection time.';
  PciEvidenceSummary =
    'PCI function and its kernel driver binding were read from sysfs.';

type
  TJsonWriter = class
  private
    FText: string;
    FEmpty: array[0..63] of Boolean;
    FDepth: Integer;
    FIndent: Integer;
    FPretty: Boolean;
    procedure OpenLevel(const Opener: Char);
    procedure CloseLevel(const Closer: Char);
    procedure PrepareMember(const Name: string);
  public
    constructor Create(Pretty: Boolean; IndentWidth: Integer);
    { Container levels. ObjectMember/ArrayMember name the level; ObjectItem
      opens one as an element of the enclosing array. }
    procedure RootObject;
    procedure EndObject;
    procedure ObjectMember(const Name: string);
    procedure ObjectItem;
    procedure ArrayMember(const Name: string);
    procedure EndArray;
    { Scalar members of an object. }
    procedure StringMember(const Name, Value: string);
    procedure IntMember(const Name: string; Value: Int64);
    procedure BoolMember(const Name: string; Value: Boolean);
    { Scalar elements of an array. }
    procedure StringItem(const Value: string);
    procedure IntItem(const Value: Int64);
    procedure BoolItem(const Value: Boolean);
    function Render: string;
  end;

{ --- JSON writer ----------------------------------------------------------- }

function JsonEscape(const Value: string): string;
var
  Index: Integer;
  Ch: Char;
begin
  Result := '"';
  for Index := 1 to Length(Value) do
  begin
    Ch := Value[Index];
    case Ch of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #8: Result := Result + '\b';
      #9: Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
    else
      if Ch < #32 then
        Result := Result + '\u00' + LowerCase(IntToHex(Ord(Ch), 2))
      else
        Result := Result + Ch;
    end;
  end;
  Result := Result + '"';
end;

constructor TJsonWriter.Create(Pretty: Boolean; IndentWidth: Integer);
begin
  inherited Create;
  FText := '';
  FDepth := 0;
  FIndent := IndentWidth;
  FPretty := Pretty;
  FEmpty[0] := True;
end;

procedure TJsonWriter.OpenLevel(const Opener: Char);
begin
  if FDepth >= High(FEmpty) then
    raise Exception.Create('json nesting too deep');
  FText := FText + Opener;
  Inc(FDepth);
  FEmpty[FDepth] := True;
end;

procedure TJsonWriter.CloseLevel(const Closer: Char);
begin
  if not FEmpty[FDepth] and FPretty then
    FText := FText + LineEnding + StringOfChar(' ', (FDepth - 1) * FIndent);
  FText := FText + Closer;
  Dec(FDepth);
end;

procedure TJsonWriter.PrepareMember(const Name: string);
begin
  if FEmpty[FDepth] then
    FEmpty[FDepth] := False
  else
    FText := FText + ',';
  if FPretty then
    FText := FText + LineEnding + StringOfChar(' ', FDepth * FIndent);
  if Name <> '' then
    FText := FText + JsonEscape(Name) + ': ';
end;

procedure TJsonWriter.RootObject;
begin
  OpenLevel('{');
end;

procedure TJsonWriter.EndObject;
begin
  CloseLevel('}');
end;

procedure TJsonWriter.ObjectMember(const Name: string);
begin
  PrepareMember(Name);
  OpenLevel('{');
end;

procedure TJsonWriter.ObjectItem;
begin
  PrepareMember('');
  OpenLevel('{');
end;

procedure TJsonWriter.ArrayMember(const Name: string);
begin
  PrepareMember(Name);
  OpenLevel('[');
end;

procedure TJsonWriter.EndArray;
begin
  CloseLevel(']');
end;

procedure TJsonWriter.StringMember(const Name, Value: string);
begin
  PrepareMember(Name);
  FText := FText + JsonEscape(Value);
end;

procedure TJsonWriter.IntMember(const Name: string; Value: Int64);
begin
  PrepareMember(Name);
  FText := FText + IntToStr(Value);
end;

procedure TJsonWriter.BoolMember(const Name: string; Value: Boolean);
begin
  PrepareMember(Name);
  if Value then
    FText := FText + 'true'
  else
    FText := FText + 'false';
end;

procedure TJsonWriter.StringItem(const Value: string);
begin
  PrepareMember('');
  FText := FText + JsonEscape(Value);
end;

procedure TJsonWriter.IntItem(const Value: Int64);
begin
  PrepareMember('');
  FText := FText + IntToStr(Value);
end;

procedure TJsonWriter.BoolItem(const Value: Boolean);
begin
  PrepareMember('');
  if Value then
    FText := FText + 'true'
  else
    FText := FText + 'false';
end;

function TJsonWriter.Render: string;
begin
  Result := FText;
end;

{ --- filesystem ------------------------------------------------------------ }

function JoinPath(const Base, Name: string): string;
begin
  if Base = '' then
    Result := Name
  else if Base[Length(Base)] = PathDelim then
    Result := Base + Name
  else
    Result := Base + PathDelim + Name;
end;

function IsDirectory(const Path: string): Boolean;
var
  Info: stat;
begin
  Result := (fpStat(PChar(Path), Info) = 0) and ((Info.st_mode and S_IFMT) = S_IFDIR);
end;

function ReadTrimmed(const Path: string): string;
var
  Stream: TFileStream;
  Buffer: array[0..4095] of Char;
  Count: LongInt;
  Raw: AnsiString;
  Offset: Integer;
begin
  Result := '';
  try
    Stream := TFileStream.Create(Path, fmOpenRead or fmShareDenyNone);
  except
    Exit;
  end;
  try
    Raw := '';
    repeat
      Count := Stream.Read(Buffer, SizeOf(Buffer));
      if Count > 0 then
      begin
        Offset := Length(Raw);
        SetLength(Raw, Offset + Count);
        Move(Buffer[0], Raw[Offset + 1], Count);
      end;
    until (Count <= 0) or (Length(Raw) >= ReadLimit);
  finally
    Stream.Free;
  end;
  Result := Trim(Raw);
end;

function ReadFact(const Path: string): string;
var
  Value, Lowered: string;
begin
  Result := '';
  Value := ReadTrimmed(Path);
  if Value = '' then
    Exit;
  Lowered := LowerCase(Value);
  if (Lowered = 'unknown') or (Lowered = 'none') or (Lowered = 'n/a') then
    Exit;
  Result := Value;
end;

function ReadCleanFact(const Path: string): string;
var
  Value, Lowered: string;
begin
  Result := '';
  Value := ReadFact(Path);
  if Value = '' then
    Exit;
  Lowered := LowerCase(Value);
  if (Lowered = 'to be filled by o.e.m.')
    or (Lowered = 'to be filled by oem')
    or (Lowered = 'default string') then
    Exit;
  Result := Value;
end;

function ReadBoolFact(const Path: string; out Value: Boolean): Boolean;
var
  Text: string;
begin
  Value := False;
  Result := False;
  Text := ReadFact(Path);
  if Text = '' then
    Exit;
  Text := LowerCase(Text);
  if (Text = '1') or (Text = 'y') or (Text = 'yes') then
  begin
    Value := True;
    Result := True;
  end
  else if (Text = '0') or (Text = 'n') or (Text = 'no') then
  begin
    Value := False;
    Result := True;
  end;
end;

function ReadIntFact(const Path: string; out Value: Int64): Boolean;
var
  Text: string;
  Parsed: Int64;
begin
  Value := 0;
  Text := ReadFact(Path);
  Result := (Text <> '') and TryStrToInt64(Text, Parsed);
  if Result then
    Value := Parsed;
end;

function ResolvedLinkTarget(const LinkPath: string): string;
var
  Info, Resolved: stat;
  Buffer: array[0..4095] of Char;
  Count: PtrInt;
  Target: string;
begin
  Result := '';
  if fpLStat(PChar(LinkPath), Info) <> 0 then
    Exit;
  if (Info.st_mode and S_IFMT) <> S_IFLNK then
    Exit;
  Count := fpReadLink(PChar(LinkPath), @Buffer[0], SizeOf(Buffer) - 1);
  if Count <= 0 then
    Exit;
  SetLength(Target, Count);
  Move(Buffer[0], Target[1], Count);
  if Target[1] <> PathDelim then
    Target := JoinPath(ExtractFileDir(LinkPath), Target);
  Target := ExpandFileName(Target);
  { resolve(strict=True) fails when the target is missing; a broken sysfs
    symlink is not a binding. }
  if fpStat(PChar(Target), Resolved) <> 0 then
    Exit;
  Result := Target;
end;

function CompareEntryNames(AList: TStringList; Index1, Index2: Integer): Integer;
begin
  { CompareStr is a byte comparison, like Python's sorted() on str names. }
  Result := CompareStr(AList[Index1], AList[Index2]);
end;

function DirectoryEntryNames(const Path: string; out Failed: Boolean): TStringList;
var
  Info: TSearchRec;
begin
  Result := TStringList.Create;
  Failed := True;
  if FindFirst(JoinPath(Path, '*'), faAnyFile, Info) <> 0 then
    Exit;
  try
    Failed := False;
    repeat
      if (Info.Name <> '.') and (Info.Name <> '..') then
        Result.Add(Info.Name);
    until FindNext(Info) <> 0;
  finally
    FindClose(Info);
  end;
  Result.CustomSort(@CompareEntryNames);
end;

{ --- collector ------------------------------------------------------------- }
{ NoDriverNotes and PciEvidenceSummary are declared once, in the program's own
  const section above. }

{ --- time -------------------------------------------------------------- }

function CivilToIso(const Epoch: Int64): string;
var
  Days, Secs, Z, Era, Doe, Yoe, Y, Doy, Mp, D, M: Int64;
begin
  Days := Epoch div 86400;
  Secs := Epoch mod 86400;
  Z := Days + 719468;
  Era := Z div 146097;
  Doe := Z - Era * 146097;
  Yoe := (Doe - Doe div 1460 + Doe div 36524 - Doe div 146096) div 365;
  Y := Yoe + Era * 400;
  Doy := Doe - (365 * Yoe + Yoe div 4 - Yoe div 100);
  Mp := (5 * Doy + 2) div 153;
  D := Doy - (153 * Mp + 2) div 5 + 1;
  if Mp < 10 then
    M := Mp + 3
  else
    M := Mp - 9;
  if M <= 2 then
    Inc(Y);
  Result := Format('%.4d-%.2d-%.2dT%.2d:%.2d:%.2dZ',
    [Y, M, D, Secs div 3600, (Secs mod 3600) div 60, Secs mod 60]);
end;

function UtcNowIso: string;
var
  Seconds: Int64;
begin
  Seconds := fpTime;
  Result := CivilToIso(Seconds);
end;

function CurrentUtcYear: Integer;
begin
  Result := StrToIntDef(Copy(UtcNowIso, 1, 4), 1970);
end;

{ --- DMI date ---------------------------------------------------------- }

function DaysInMonth(Year, Month: Integer): Integer;
const
  Lengths: array[1..12] of Integer = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31);
begin
  Result := Lengths[Month];
  if (Month = 2) and (Year mod 4 = 0)
    and ((Year mod 100 <> 0) or (Year mod 400 = 0)) then
    Result := 29;
end;

function SplitThree(const Value: string; Delimiter: Char;
  out First, Second, Third: string): Boolean;
var
  FirstAt, SecondAt: Integer;
begin
  Result := False;
  First := '';
  Second := '';
  Third := '';
  FirstAt := Pos(Delimiter, Value);
  if FirstAt = 0 then
    Exit;
  SecondAt := Pos(Delimiter, Copy(Value, FirstAt + 1, Length(Value)));
  if SecondAt = 0 then
    Exit;
  SecondAt := SecondAt + FirstAt;
  if Pos(Delimiter, Copy(Value, SecondAt + 1, Length(Value))) <> 0 then
    Exit;
  First := Copy(Value, 1, FirstAt - 1);
  Second := Copy(Value, FirstAt + 1, SecondAt - FirstAt - 1);
  Third := Copy(Value, SecondAt + 1, Length(Value) - SecondAt);
  Result := True;
end;

{ collector.py::_normalise_bios_date - DMI writes MM/DD/YYYY; the schema
  field is a plain ISO date. An unparseable or out-of-range date yields '',
  so the field is omitted instead of carrying a vendor string. }
function NormaliseBiosDate(const Raw: string): string;
var
  Value, First, Second, Third: string;
  Year, Month, Day: Integer;
begin
  Result := '';
  if Raw = '' then
    Exit;
  Value := Trim(Raw);
  if SplitThree(Value, '/', First, Second, Third) then
  begin
    if not (TryStrToInt(First, Month) and TryStrToInt(Second, Day)
      and TryStrToInt(Third, Year)) then
      Exit;
  end
  else if SplitThree(Value, '-', First, Second, Third) then
  begin
    if not (TryStrToInt(First, Year) and TryStrToInt(Second, Month)
      and TryStrToInt(Third, Day)) then
      Exit;
  end
  else
    Exit;
  if (Month < 1) or (Month > 12) then
    Exit;
  if (Day < 1) or (Day > DaysInMonth(Year, Month)) then
    Exit;
  if (Year < 1990) or (Year > CurrentUtcYear + 1) then
    Exit;
  Result := Format('%.4d-%.2d-%.2d', [Year, Month, Day]);
end;

{ --- boot mode --------------------------------------------------------- }

function IsX86Machine(const Architecture: string): Boolean;
var
  Lowered: string;
begin
  Lowered := LowerCase(Architecture);
  Result := (Lowered = 'x86_64') or (Lowered = 'amd64') or (Lowered = 'i386')
    or (Lowered = 'i486') or (Lowered = 'i586') or (Lowered = 'i686')
    or (Lowered = 'x86');
end;

{ collector.py::_boot_mode - never guesses the firmware type. The EFI
  directory is positive evidence; its absence is evidence only on x86, where
  the alternative is a legacy BIOS/CSM handoff. }
function BootModeOf(const SysfsRoot, Architecture: string; out Evidence: string): string;
begin
  if IsDirectory(JoinPath(SysfsRoot, 'firmware/efi')) then
  begin
    Evidence := 'sysfs:/firmware/efi is present: the kernel was booted through EFI.';
    Exit('uefi');
  end;
  if IsX86Machine(Architecture)
    and IsDirectory(JoinPath(SysfsRoot, 'class/dmi/id')) then
  begin
    Evidence := 'sysfs:/firmware/efi is absent while x86 DMI identity is present: '
      + 'the firmware handed the kernel over in legacy BIOS/CSM mode.';
    Exit('bios');
  end;
  Evidence := 'Neither sysfs:/firmware/efi nor an x86 DMI identity is available, '
    + 'so the boot mode is not determined.';
  Result := 'unknown';
end;

{ --- architecture ------------------------------------------------------ }

function CharArrayToStr(P: PChar; MaxLength: Integer): string;
var
  Index: Integer;
begin
  Index := 0;
  while (Index < MaxLength) and (P[Index] <> #0) do
    Inc(Index);
  SetLength(Result, Index);
  if Index > 0 then
    Move(P[0], Result[1], Index);
end;

function MachineName: string;
var
  Info: utsname;
begin
  Result := '';
  if fpUname(Info) = 0 then
    Result := CharArrayToStr(@Info.machine[0], 64);
end;

function KernelReleaseName: string;
var
  Info: utsname;
begin
  Result := '';
  if fpUname(Info) = 0 then
    Result := CharArrayToStr(@Info.release[0], 64);
end;

{ --- PCI class --------------------------------------------------------- }

function PciCategory(const ClassValue: string): string;
var
  Value: string;
begin
  if ClassValue = '' then
    Exit('other');
  Value := LowerCase(ClassValue);
  if Copy(Value, 1, 2) = '0x' then
    Value := Copy(Value, 3, Length(Value));
  if Copy(Value, 1, 2) = '03' then
    Exit('gpu');
  if Copy(Value, 1, 2) = '02' then
    Exit('network');
  if Copy(Value, 1, 2) = '04' then
    Exit('audio');
  if Copy(Value, 1, 2) = '01' then
    Exit('storage-controller');
  if Copy(Value, 1, 4) = '0c03' then
    Exit('usb-controller');
  Result := 'other';
end;

{ --- device objects ---------------------------------------------------- }

procedure WriteDriverObject(W: TJsonWriter; const DevicePath: string);
var
  Target, ModuleTarget: string;
begin
  W.ObjectMember('driver');
  if not IsDirectory(DevicePath) then
  begin
    W.StringMember('status', 'unknown');
    W.EndObject;
    Exit;
  end;
  Target := ResolvedLinkTarget(JoinPath(DevicePath, 'driver'));
  if Target = '' then
  begin
    W.StringMember('notes', NoDriverNotes);
    W.StringMember('status', 'none-known');
    W.EndObject;
    Exit;
  end;
  W.StringMember('bound_driver', ExtractFileName(ExcludeTrailingPathDelimiter(Target)));
  ModuleTarget := ResolvedLinkTarget(JoinPath(JoinPath(DevicePath, 'driver'), 'module'));
  if ModuleTarget <> '' then
  begin
    W.StringMember('module', ExtractFileName(ExcludeTrailingPathDelimiter(ModuleTarget)));
    W.BoolMember('module_loaded', True);
  end;
  W.StringMember('status', 'bound');
  W.EndObject;
end;

procedure WriteIdentity(W: TJsonWriter; const Entry, EntryName: string);
var
  Value: string;
begin
  W.ObjectMember('identity');
  Value := ReadFact(JoinPath(Entry, 'class'));
  if Value <> '' then
    W.StringMember('class_id', Value);
  Value := ReadFact(JoinPath(Entry, 'device'));
  if Value <> '' then
    W.StringMember('device_id', Value);
  W.StringMember('local_path', '/bus/pci/devices/' + EntryName);
  Value := ReadFact(JoinPath(Entry, 'modalias'));
  if Value <> '' then
    W.StringMember('modalias', Value);
  Value := ReadFact(JoinPath(Entry, 'revision'));
  if Value <> '' then
    W.StringMember('revision', Value);
  Value := ReadFact(JoinPath(Entry, 'subsystem_device'));
  if Value <> '' then
    W.StringMember('subsystem_device_id', Value);
  Value := ReadFact(JoinPath(Entry, 'subsystem_vendor'));
  if Value <> '' then
    W.StringMember('subsystem_vendor_id', Value);
  Value := ReadFact(JoinPath(Entry, 'vendor'));
  if Value <> '' then
    W.StringMember('vendor_id', Value);
  W.EndObject;
end;

{ collector.py::_gpu_facts - every fact is optional, and whatever no source
  provided is listed in `unavailable` instead of being defaulted. }
procedure WriteGpuFacts(W: TJsonWriter; const Entry: string);
var
  Unavailable: TStringList;
  Names: TStringList;
  Cards: TStringList;
  ListFailed, HasCards, HasBootVga, BootVga: Boolean;
  HasCurrentSpeed, HasMaxSpeed, HasCurrentWidth, HasMaxWidth: Boolean;
  CurrentSpeed, MaxSpeed: string;
  CurrentWidth, MaxWidth: Int64;
  Index: Integer;
  DrmPath: string;
begin
  Unavailable := TStringList.Create;
  Cards := TStringList.Create;
  Names := nil;
  try
    HasBootVga := ReadBoolFact(JoinPath(Entry, 'boot_vga'), BootVga);

    HasCards := False;
    DrmPath := JoinPath(Entry, 'drm');
    if IsDirectory(DrmPath) then
    begin
      Names := DirectoryEntryNames(DrmPath, ListFailed);
      if ListFailed then
        Names.Free
      else
      begin
        for Index := 0 to Names.Count - 1 do
          if Copy(Names[Index], 1, 4) = 'card' then
            Cards.Add(Names[Index]);
        HasCards := True;
        Names.Free;
      end;
      Names := nil;
    end;

    CurrentSpeed := ReadFact(JoinPath(Entry, 'current_link_speed'));
    HasCurrentSpeed := CurrentSpeed <> '';
    MaxSpeed := ReadFact(JoinPath(Entry, 'max_link_speed'));
    HasMaxSpeed := MaxSpeed <> '';
    HasCurrentWidth := ReadIntFact(JoinPath(Entry, 'current_link_width'), CurrentWidth);
    HasMaxWidth := ReadIntFact(JoinPath(Entry, 'max_link_width'), MaxWidth);

    if not HasBootVga then
      Unavailable.Add('boot_vga');
    if not HasCards then
      Unavailable.Add('drm_cards');
    if not HasCurrentSpeed then
      Unavailable.Add('pci_link.current_speed');
    if not HasMaxSpeed then
      Unavailable.Add('pci_link.max_speed');
    if not HasCurrentWidth then
      Unavailable.Add('pci_link.current_width');
    if not HasMaxWidth then
      Unavailable.Add('pci_link.max_width');

    W.ObjectMember('gpu');
    if HasBootVga then
      W.BoolMember('boot_vga', BootVga);
    if HasCards then
    begin
      W.ArrayMember('drm_cards');
      for Index := 0 to Cards.Count - 1 do
        W.StringItem(Cards[Index]);
      W.EndArray;
    end;
    if HasCurrentSpeed or HasMaxSpeed or HasCurrentWidth or HasMaxWidth then
    begin
      W.ObjectMember('pci_link');
      if HasCurrentSpeed then
        W.StringMember('current_speed', CurrentSpeed);
      if HasCurrentWidth then
        W.IntMember('current_width', CurrentWidth);
      if HasMaxSpeed then
        W.StringMember('max_speed', MaxSpeed);
      if HasMaxWidth then
        W.IntMember('max_width', MaxWidth);
      W.EndObject;
    end;
    if Unavailable.Count > 0 then
    begin
      W.ArrayMember('unavailable');
      for Index := 0 to Unavailable.Count - 1 do
        W.StringItem(Unavailable[Index]);
      W.EndArray;
    end;
    W.EndObject;
  finally
    if Names <> nil then
      Names.Free;
    Cards.Free;
    Unavailable.Free;
  end;
end;

procedure WriteGpuDevice(W: TJsonWriter; const SysfsRoot, EntryName,
  ObservedAt: string);
var
  Entry: string;
begin
  Entry := JoinPath(JoinPath(SysfsRoot, 'bus/pci/devices'), EntryName);
  W.ObjectItem;
  W.StringMember('bus', 'pci');
  W.StringMember('category', 'gpu');
  W.StringMember('device_id', 'pci-' + EntryName);
  W.StringMember('discovery_status', 'discovered');
  WriteDriverObject(W, Entry);
  W.ArrayMember('evidence');
  W.ObjectItem;
  W.StringMember('confidence', 'confirmed');
  W.StringMember('kind', 'live-observation');
  W.StringMember('observed_at', ObservedAt);
  W.StringMember('source', 'sysfs:/bus/pci/devices/' + EntryName);
  W.StringMember('summary', PciEvidenceSummary);
  W.EndObject;
  W.EndArray;
  W.ObjectMember('firmware');
  W.StringMember('redistribution_status', 'unknown');
  W.StringMember('requirement', 'unknown');
  W.StringMember('runtime_status', 'unknown');
  W.EndObject;
  W.ArrayMember('functional_tests');
  W.EndArray;
  WriteGpuFacts(W, Entry);
  WriteIdentity(W, Entry, EntryName);
  W.ArrayMember('recommendations');
  W.EndArray;
  W.EndObject;
end;

procedure WriteDevices(W: TJsonWriter; const SysfsRoot, ObservedAt: string);
var
  Names: TStringList;
  ListFailed: Boolean;
  Index: Integer;
  Entry, Vendor, Product: string;
begin
  W.ArrayMember('devices');
  Names := DirectoryEntryNames(JoinPath(SysfsRoot, 'bus/pci/devices'), ListFailed);
  try
    if not ListFailed then
      for Index := 0 to Names.Count - 1 do
      begin
        Entry := JoinPath(JoinPath(SysfsRoot, 'bus/pci/devices'), Names[Index]);
        Vendor := ReadFact(JoinPath(Entry, 'vendor'));
        Product := ReadFact(JoinPath(Entry, 'device'));
        if (Vendor = '') and (Product = '') then
          Continue;
        if PciCategory(ReadFact(JoinPath(Entry, 'class'))) <> 'gpu' then
          Continue;
        WriteGpuDevice(W, SysfsRoot, Names[Index], ObservedAt);
      end;
  finally
    Names.Free;
  end;
  W.EndArray;
end;

{ --- virtualization ---------------------------------------------------- }

function VirtualizationOf(const SysfsRoot, SystemVendor, ProductName,
  BoardName: string): string;
var
  Marker, Combined: string;
begin
  Marker := LowerCase(ReadFact(JoinPath(SysfsRoot, 'hypervisor/type')));
  if Marker <> '' then
  begin
    if Pos('kvm', Marker) > 0 then
      Exit('kvm');
    if Pos('xen', Marker) > 0 then
      Exit('xen');
  end;
  Combined := LowerCase(SystemVendor + ' ' + ProductName + ' ' + BoardName);
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

{ --- report ------------------------------------------------------------ }

function NewReportId: string;
var
  Index: Integer;
begin
  Result := 'wsm-';
  for Index := 1 to 12 do
    Result := Result + LowerCase(IntToHex(Random(256), 2));
end;

function RenderReport(const SysfsRoot, ProcRoot: string; Pretty: Boolean): string;
var
  W: TJsonWriter;
  ObservedAt, Architecture, KernelRelease, BootMode, Evidence: string;
  BiosRelease, BiosDate, Virtualization: string;
  SystemVendor, ProductName, BoardName: string;
begin
  Randomize;
  ObservedAt := UtcNowIso;

  Architecture := MachineName;
  if Architecture = '' then
    Architecture := 'unknown';

  KernelRelease := ReadFact(JoinPath(ProcRoot, 'sys/kernel/osrelease'));
  if KernelRelease = '' then
  begin
    KernelRelease := KernelReleaseName;
    if KernelRelease = '' then
      KernelRelease := 'unknown';
  end;

  { The BIOS fields are the third fact group; the other DMI identity fields
    are read only to classify the virtualization environment, which the
    schema requires and which this slice does not otherwise report. }
  BiosRelease := ReadCleanFact(JoinPath(SysfsRoot, 'class/dmi/id/bios_release'));
  BiosDate := NormaliseBiosDate(ReadFact(JoinPath(SysfsRoot, 'class/dmi/id/bios_date')));
  SystemVendor := ReadCleanFact(JoinPath(SysfsRoot, 'class/dmi/id/sys_vendor'));
  ProductName := ReadCleanFact(JoinPath(SysfsRoot, 'class/dmi/id/product_name'));
  BoardName := ReadCleanFact(JoinPath(SysfsRoot, 'class/dmi/id/board_name'));

  BootMode := BootModeOf(SysfsRoot, Architecture, Evidence);
  Virtualization := VirtualizationOf(SysfsRoot, SystemVendor, ProductName, BoardName);

  W := TJsonWriter.Create(Pretty, 2);
  try
    W.RootObject;

    W.StringMember('collected_at', ObservedAt);

    W.ArrayMember('collectors');
    W.ObjectItem;
    W.BoolMember('available', True);
    W.StringMember('name', 'wsm-hwcheck-fpc-sysfs');
    W.StringMember('notes',
      'First FPC vertical slice: boot mode, the GPU record and BIOS release/date only. '
      + 'Reads sysfs/procfs only. No network requests or system mutations.');
    W.StringMember('scope', 'unprivileged-read-only');
    W.StringMember('version', ToolVersion);
    W.EndObject;
    W.ObjectItem;
    W.BoolMember('available', False);
    W.StringMember('name', 'wsm-hwcheck-fpc-unported-groups');
    W.StringMember('notes',
      'CPU, USB, block devices, DRM connectors, runtime diagnostics and the '
      + 'pci.ids naming database are not collected by this slice.');
    W.StringMember('scope', 'unprivileged-read-only');
    W.EndObject;
    W.EndArray;

    WriteDevices(W, SysfsRoot, ObservedAt);

    W.ObjectMember('environment');
    W.StringMember('architecture', Architecture);
    W.StringMember('boot_mode', BootMode);
    W.StringMember('boot_mode_evidence', Evidence);
    W.StringMember('kernel_release', KernelRelease);
    if (BiosRelease <> '') or (BiosDate <> '') then
    begin
      W.ObjectMember('platform');
      if BiosDate <> '' then
        W.StringMember('bios_date', BiosDate);
      if BiosRelease <> '' then
        W.StringMember('bios_release', BiosRelease);
      W.EndObject;
    end;
    W.StringMember('virtualization', Virtualization);
    W.EndObject;

    W.ArrayMember('limitations');
    W.StringItem('Inventory and driver evidence do not prove end-to-end device functionality.');
    W.StringItem('Boot mode is derived from sysfs:/firmware/efi; UEFI firmware booted '
      + 'through CSM is reported as bios, and a platform where neither source is '
      + 'readable stays unknown.');
    W.StringItem('This is the FPC vertical slice: only boot mode, the GPU record and '
      + 'BIOS release/date are collected, so an absent group here is not evidence '
      + 'that the machine lacks it.');
    W.StringItem('PCI model names come from the local pci.ids file when one exists; '
      + 'this slice does not read that database, so a name is never guessed from an id.');
    W.StringItem('No remote hardware database lookup or probe upload is performed.');
    W.EndArray;

    W.ObjectMember('privacy');
    W.BoolMember('network_requests_performed', False);
    W.BoolMember('network_upload_performed', False);
    W.StringMember('profile', 'strict-local');
    W.ArrayMember('redactions_applied');
    W.StringItem('serial-number');
    W.StringItem('mac-address');
    W.StringItem('uuid');
    W.StringItem('hostname');
    W.StringItem('username');
    W.StringItem('ip-address');
    W.StringItem('storage-wwn');
    W.EndArray;
    W.BoolMember('sensitive_identifiers_included', False);
    W.EndObject;

    W.StringMember('report_id', NewReportId);
    W.StringMember('schema_version', SchemaVersion);

    W.ArrayMember('warnings');
    W.StringItem('This report comes from the FPC vertical slice; groups outside '
      + 'boot mode, the GPU record and BIOS release/date are not collected.');
    W.EndArray;

    W.EndObject;
    Result := W.Render;
  finally
    W.Free;
  end;
end;

{ --- command line ---------------------------------------------------------- }

var
  SysfsRoot: string = '/sys';
  ProcRoot: string = '/proc';
  OutputPath: string = '';
  Compact: Boolean = False;
  Rendered: string;

procedure Usage;
begin
  WriteLn('usage: ', ProgName, ' [--version] [--output PATH] [--compact]');
  WriteLn;
  WriteLn('Collect a local-only, read-only Linux hardware and driver/firmware');
  WriteLn('evidence report. This build collects the boot mode, the GPU record');
  WriteLn('and the BIOS release/date only.');
end;

function NextValue(var Position: Integer; const Option: string): string;
begin
  Inc(Position);
  if Position > ParamCount then
  begin
    WriteLn(StdErr, ProgName, ': ', Option, ' requires a value');
    Halt(2);
  end;
  Result := ParamStr(Position);
end;

procedure Fail(const Message: string);
begin
  WriteLn(StdErr, ProgName, ': ', Message);
  Halt(2);
end;

procedure ParseArguments;
var
  Position: Integer;
  Argument: string;
begin
  Position := 1;
  while Position <= ParamCount do
  begin
    Argument := ParamStr(Position);
    if (Argument = '--version') then
    begin
      WriteLn(ProgName, ' ', ToolVersion);
      Halt(0);
    end
    else if (Argument = '--help') or (Argument = '-h') then
    begin
      Usage;
      Halt(0);
    end
    else if Argument = '--compact' then
      Compact := True
    else if Argument = '--output' then
      OutputPath := NextValue(Position, '--output')
    else if Copy(Argument, 1, 9) = '--output=' then
      OutputPath := Copy(Argument, 10, Length(Argument))
    else if Argument = '--sysfs-root' then
      SysfsRoot := NextValue(Position, '--sysfs-root')
    else if Copy(Argument, 1, 13) = '--sysfs-root=' then
      SysfsRoot := Copy(Argument, 14, Length(Argument))
    else if Argument = '--proc-root' then
      ProcRoot := NextValue(Position, '--proc-root')
    else if Copy(Argument, 1, 12) = '--proc-root=' then
      ProcRoot := Copy(Argument, 13, Length(Argument))
    else
    begin
      WriteLn(StdErr, ProgName, ': unrecognised argument: ', Argument);
      Halt(2);
    end;
    Inc(Position);
  end;
end;

procedure WriteTextFile(const Path, Text: string);
var
  Stream: TFileStream;
begin
  Stream := TFileStream.Create(Path, fmCreate);
  try
    if Length(Text) > 0 then
      Stream.WriteBuffer(Text[1], Length(Text));
  finally
    Stream.Free;
  end;
end;

begin
  ParseArguments;
  try
    Rendered := RenderReport(SysfsRoot, ProcRoot, not Compact) + LineEnding;
    if OutputPath <> '' then
      WriteTextFile(OutputPath, Rendered)
    else
      Write(Rendered);
  except
    on Error: Exception do
      Fail(Error.Message);
  end;
  Halt(0);
end.
