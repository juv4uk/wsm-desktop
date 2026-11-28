{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-partition, FPC edition: build a disk layout, or refuse with a reason.

  This unit PLANS. It never runs sgdisk, never opens a block device, and never
  writes anything. `commands' are printed as data; the caller decides whether to
  execute them, and the caller is Python, which has the consent chain.

  Refusal order is copied from wsm_install/partition.py because order carries
  meaning: the cheapest and most dangerous checks come first, so a caller
  reading only the first error still learns the most important thing.

  Two refusals that exist for reasons easy to lose in a port:
    * `holds_running_system' - the disk we booted from is never a target;
    * acknowledgement must name EXACTLY the device. Absence of a discovered
      filesystem is not consent to erase the disk: --zap-all replaces the
      partition table whether or not we recognised what was on it.
}
program wsm_partition;

{$mode objfpc}{$H+}

uses
  SysUtils;

const
  EspMib = 512;
  BiosBootMib = 1;
  MinRootMib = 12 * 1024;
  SizeTolerancePercent = 2;

type
  TDisk = record
    Path: string;
    SizeBytes: Int64;
    HoldsRunningSystem: Boolean;
  end;

  TPartition = record
    Number: Integer;
    StartMib: Integer;
    EndMib: Integer;      { 0 means "to the end of the disk" }
    TypeCode: string;
    Name: string;
    Role: string;
  end;

  TLayout = record
    Firmware: string;
    DiskPath: string;
    DiskSizeBytes: Int64;
    Parts: array of TPartition;
  end;

procedure Refuse(const Code, Message: string);
begin
  WriteLn(StdErr, 'refused:', Code, ': ', Message);
  Halt(10);
end;

{ Whole block devices only. A partition (nvme0n1p1, sda1) or an image file is
  never a valid target, and guessing would erase the wrong thing. }
function IsAsciiLowerLetters(const Value: string): Boolean;
var
  I: Integer;
begin
  Result := Value <> '';
  for I := 1 to Length(Value) do
    if not ((Value[I] >= 'a') and (Value[I] <= 'z')) then
      Exit(False);
end;

function IsAsciiDigits(const Value: string): Boolean;
var
  I: Integer;
begin
  Result := Value <> '';
  for I := 1 to Length(Value) do
    if not ((Value[I] >= '0') and (Value[I] <= '9')) then
      Exit(False);
end;

function IsWholeBlockDevice(const Path: string): Boolean;
var
  Base, Suffix: string;
  Index, DigitStart: Integer;
begin
  Result := False;
  if Copy(Path, 1, 5) <> '/dev/' then
    Exit;
  Base := Copy(Path, 6, Length(Path) - 5);
  if Base = '' then
    Exit;

  { Match Python DEVICE_PATH exactly: sd[a-z]+ and vd[a-z]+. }
  if (Copy(Base, 1, 2) = 'sd') or (Copy(Base, 1, 2) = 'vd') then
  begin
    Suffix := Copy(Base, 3, Length(Base) - 2);
    Result := IsAsciiLowerLetters(Suffix);
    Exit;
  end;

  { NVMe namespace: nvme[0-9]+n[0-9]+; partitions have a trailing pN. }
  if Copy(Base, 1, 4) = 'nvme' then
  begin
    Index := 5;
    while Index <= Length(Base) do
    begin
      if not ((Base[Index] >= '0') and (Base[Index] <= '9')) then
        Break;
      Inc(Index);
    end;
    if Index = 5 then Exit;
    if Index > Length(Base) then Exit;
    if Base[Index] <> 'n' then Exit;
    Inc(Index);
    DigitStart := Index;
    while Index <= Length(Base) do
    begin
      if not ((Base[Index] >= '0') and (Base[Index] <= '9')) then
        Exit;
      Inc(Index);
    end;
    Result := Index > DigitStart;
    Exit;
  end;

  { MMC whole disk: mmcblk[0-9]+; mmcblk0p1 is a partition. }
  if Copy(Base, 1, 6) = 'mmcblk' then
  begin
    Suffix := Copy(Base, 7, Length(Base) - 6);
    Result := IsAsciiDigits(Suffix);
    Exit;
  end;
end;

procedure ValidateTarget(const Disk: TDisk; const Acknowledgement, Firmware: string;
  ExpectedSize: Int64);
var
  Minimum, Delta: Int64;
begin
  if not IsWholeBlockDevice(Disk.Path) then
    Refuse('disk.path',
      '''' + Disk.Path + ''' is not a whole block device; partitions and images are refused');

  if (Firmware <> 'uefi') and (Firmware <> 'bios') then
    Refuse('disk.firmware', 'firmware must be ''uefi'' or ''bios'', got ''' + Firmware + '''');

  if Disk.HoldsRunningSystem then
    Refuse('disk.running-system', Disk.Path + ' holds the system we are running from');

  Minimum := (MinRootMib + EspMib) * 1024 * 1024;
  if Disk.SizeBytes < Minimum then
    Refuse('disk.too-small',
      Format('%s is %d bytes; the smallest supported layout needs %d MiB',
             [Disk.Path, Disk.SizeBytes, MinRootMib + EspMib]));

  if Acknowledgement <> Disk.Path then
    Refuse('disk.acknowledgement',
      'refusing destructive partition-table replacement without an acknowledgement ' +
      'that names exactly ''' + Disk.Path + ''' (got ''' + Acknowledgement + ''')');

  if ExpectedSize > 0 then
  begin
    Delta := Disk.SizeBytes - ExpectedSize;
    if Delta < 0 then
      Delta := -Delta;
    { Compare without multiplying 64-bit sizes or rounding fractional drift down. }
    if Delta > (ExpectedSize div (100 div SizeTolerancePercent)) then
      Refuse('disk.size-drift',
        Format('%s reports %d bytes but %d was expected (more than %d%% drift); ' +
               'the disk may have been replaced',
               [Disk.Path, Disk.SizeBytes, ExpectedSize, SizeTolerancePercent]));
  end;
end;

procedure AddPart(var Layout: TLayout; Number, StartMib, EndMib: Integer;
  const TypeCode, Name, Role: string);
var
  Index: Integer;
begin
  Index := Length(Layout.Parts);
  SetLength(Layout.Parts, Index + 1);
  Layout.Parts[Index].Number := Number;
  Layout.Parts[Index].StartMib := StartMib;
  Layout.Parts[Index].EndMib := EndMib;
  Layout.Parts[Index].TypeCode := TypeCode;
  Layout.Parts[Index].Name := Name;
  Layout.Parts[Index].Role := Role;
end;

function BuildPlan(const Disk: TDisk; const Firmware, Acknowledgement: string;
  ExpectedSize: Int64): TLayout;
var
  Cursor: Integer;
begin
  ValidateTarget(Disk, Acknowledgement, Firmware, ExpectedSize);

  Result.Firmware := Firmware;
  Result.DiskPath := Disk.Path;
  Result.DiskSizeBytes := Disk.SizeBytes;
  SetLength(Result.Parts, 0);

  Cursor := 1;
  if Firmware = 'bios' then
  begin
    AddPart(Result, 1, Cursor, Cursor + BiosBootMib, 'ef02', 'wsm-bios-boot', 'bios-grub');
    Inc(Cursor, BiosBootMib);
  end
  else
  begin
    AddPart(Result, 1, Cursor, Cursor + EspMib, 'ef00', 'wsm-esp', 'esp');
    Inc(Cursor, EspMib);
  end;

  { End 0 means "rest of the disk"; sgdisk reads it that way. }
  AddPart(Result, Length(Result.Parts) + 1, Cursor, 0, '8300', 'wsm-root', 'root');
end;

procedure EmitLayout(const Layout: TLayout);
var
  I: Integer;
  EndText: string;
begin
  Write('{"firmware":"', Layout.Firmware, '"');
  Write(',"disk":"', Layout.DiskPath, '"');
  Write(',"disk_size_bytes":', Layout.DiskSizeBytes);
  Write(',"partitions":[');
  for I := 0 to High(Layout.Parts) do
  begin
    if I > 0 then Write(',');
    if Layout.Parts[I].EndMib = 0 then
      EndText := '0'
    else
      EndText := IntToStr(Layout.Parts[I].EndMib) + 'MiB';
    Write('{"number":', Layout.Parts[I].Number);
    Write(',"start":"', Layout.Parts[I].StartMib, 'MiB"');
    Write(',"end":"', EndText, '"');
    Write(',"typecode":"', Layout.Parts[I].TypeCode, '"');
    Write(',"name":"', Layout.Parts[I].Name, '"');
    Write(',"role":"', Layout.Parts[I].Role, '"}');
  end;
  Write('],"commands":[');
  Write('["sgdisk","--zap-all","', Layout.DiskPath, '"]');
  for I := 0 to High(Layout.Parts) do
  begin
    Write(',["sgdisk","--new=', Layout.Parts[I].Number, ':', Layout.Parts[I].StartMib, 'MiB:');
    if Layout.Parts[I].EndMib = 0 then Write('0') else Write(Layout.Parts[I].EndMib, 'MiB');
    Write('","--typecode=', Layout.Parts[I].Number, ':', Layout.Parts[I].TypeCode);
    Write('","--change-name=', Layout.Parts[I].Number, ':', Layout.Parts[I].Name);
    Write('","', Layout.DiskPath, '"]');
  end;
  Write('],"executed":false');
  WriteLn('}');
end;

var
  Disk: TDisk;
  Firmware, Acknowledgement, Arg: string;
  ExpectedSize: Int64;
  I: Integer;
  Layout: TLayout;
begin
  Firmware := '';
  Acknowledgement := '';
  ExpectedSize := 0;
  Disk.Path := '';
  Disk.SizeBytes := 0;
  Disk.HoldsRunningSystem := False;

  I := 1;
  while I <= ParamCount do
  begin
    Arg := ParamStr(I);
    if (Arg = '--disk') and (I < ParamCount) then
    begin
      Disk.Path := ParamStr(I + 1); Inc(I, 2);
    end
    else if (Arg = '--size') and (I < ParamCount) then
    begin
      Disk.SizeBytes := StrToInt64Def(ParamStr(I + 1), 0); Inc(I, 2);
    end
    else if (Arg = '--firmware') and (I < ParamCount) then
    begin
      Firmware := ParamStr(I + 1); Inc(I, 2);
    end
    else if (Arg = '--ack') and (I < ParamCount) then
    begin
      Acknowledgement := ParamStr(I + 1); Inc(I, 2);
    end
    else if (Arg = '--expected-size') and (I < ParamCount) then
    begin
      ExpectedSize := StrToInt64Def(ParamStr(I + 1), 0); Inc(I, 2);
    end
    else if Arg = '--holds-running-system' then
    begin
      Disk.HoldsRunningSystem := True; Inc(I);
    end
    else
    begin
      WriteLn(StdErr, 'usage: wsm-partition --disk DEV --size BYTES --firmware uefi|bios ',
                      '--ack DEV [--expected-size BYTES] [--holds-running-system]');
      Halt(2);
    end;
  end;

  if (Disk.Path = '') or (Disk.SizeBytes <= 0) or (Firmware = '') then
  begin
    WriteLn(StdErr, 'usage: wsm-partition --disk DEV --size BYTES --firmware uefi|bios ',
                    '--ack DEV [--expected-size BYTES] [--holds-running-system]');
    Halt(2);
  end;

  Layout := BuildPlan(Disk, Firmware, Acknowledgement, ExpectedSize);
  EmitLayout(Layout);
end.
