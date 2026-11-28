{ SPDX-License-Identifier: LicenseRef-Volnist }
{ }
{ wsm-hwcheck-pascal — перший FPC-зріз колектора доказів. }
{ }
{ Навіщо: wsm_hwcheck/ сьогодні це 2241 рядок Python, і кожен виклик }
{ платить ~62 мс за старт інтерпретатора, а пакет тягне CPython у closure }
{ (записано в wsm/packages/wsm.scm: ~226 МБ із 399 МБ паку були збірками }
{ Python). FPC дає статичний бінарник без libc-залежностей — саме так }
{ зроблено в gp107-nvidia-re. }
{ }
{ ЦЕ ПЕРШИЙ ЗРІЗ, А НЕ ЗАМІНА. Він збирає лише блок identity: архітектура, }
{ ядро, режим завантаження, PCI-пристрої з vendor:device і прив'язаним }
{ драйвером. Решта звіту (firmware, ISA-контракт, діагностика модулів) }
{ лишається в Python, доки паритетний тест не доведе, що переносити є сенс. }
{ }
{ Статус: НЕ ЗІБРАНО в середовищі, де це писали — там немає fpc. }
{ Перевіряється tests/test_fpc_collector_parity.py: якщо fpc немає, тест }
{ позначається skipped і прямо каже, що паритет не доведено. }
{ }
{ Збірка: }
{   fpc -O2 -CX -XX -Xs tools/fpc/wsm_hwcheck.pas }
{ }
{ Вивід: ті самі ключі, що їх дає Python-колектор для блоку environment і }
{ списку pci-пристроїв, у стабільному порядку — щоб паритет можна було }
{ порівнювати текстом, а не «на око». }

program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix, Unix;

const
  SysRoot = '/sys';
  ProcRoot = '/proc';
  MaxDevices = 512;

type
  TDevice = record
    Address: string;      { 0000:01:00.0 }
    Vendor: string;       { 10de }
    Device: string;       { 1c82 }
    ClassCode: string;    { 0x030000 }
    Driver: string;       { nvidia | '' }
    Module: string;       { nvidia | '' — порожньо, якщо драйвер вбудований }
  end;

var
  Devices: array[0..MaxDevices - 1] of TDevice;
  DeviceCount: Integer = 0;

function ReadFirstLine(const Path: string): string;
var
  Stream: TFileStream;
  Buffer: array[0..1023] of Char;
  Read: LongInt;
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
    Read := Stream.Read(Buffer, SizeOf(Buffer) - 1);
    if Read > 0 then
    begin
      Buffer[Read] := #0;
      Result := Trim(string(PChar(@Buffer[0])));
    end;
  finally
    Stream.Free;
  end;
end;

{ Драйвер, прив'язаний до пристрою, — це symlink на модуль у sysfs.
  Читаємо через fpReadLink, а не через shell: жодних зовнішніх команд. }
function ReadDriverLink(const DevicePath: string): string;
var
  LinkTarget: array[0..1023] of Char;
  Count: LongInt;
  Base: string;
begin
  Result := '';
  FillChar(LinkTarget, SizeOf(LinkTarget), 0);
  Count := fpReadLink(DevicePath + '/driver', @LinkTarget[0], SizeOf(LinkTarget) - 1);
  if Count <= 0 then
    Exit;
  LinkTarget[Count] := #0;
  Base := string(PChar(@LinkTarget[0]));
  Result := ExtractFileName(Base);
end;

{ Модуль ядра за прив'язаним драйвером. Порожній результат — не помилка:
  драйвер може бути вбудований у ядро, і тоді symlink module просто відсутній.
  Python-колектор фіксує це так само: status=bound без module. }
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

procedure ScanPciDevices;
var
  Dir: TSearchRec;
  DevicePath, Address: string;
begin
  DeviceCount := 0;
  if FindFirst(SysRoot + '/bus/pci/devices/*', faDirectory, Dir) <> 0 then
    Exit;
  try
    repeat
      if (Dir.Name = '.') or (Dir.Name = '..') then
        Continue;
      if DeviceCount >= MaxDevices then
        Break;
      Address := Dir.Name;
      DevicePath := SysRoot + '/bus/pci/devices/' + Address;
      Devices[DeviceCount].Address := Address;
      Devices[DeviceCount].Vendor := ReadFirstLine(DevicePath + '/vendor');
      Devices[DeviceCount].Device := ReadFirstLine(DevicePath + '/device');
      Devices[DeviceCount].ClassCode := ReadFirstLine(DevicePath + '/class');
      Devices[DeviceCount].Driver := ReadDriverLink(DevicePath);
      Devices[DeviceCount].Module := ReadModuleLink(DevicePath);
      Inc(DeviceCount);
    until FindNext(Dir) <> 0;
  finally
    FindClose(Dir);
  end;
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

{ Порядок ключів фіксований: паритетний тест порівнює текст, тому }
{ «приблизно той самий JSON» тут не годиться. }
procedure EmitReport;
var
  Index: Integer;
  Separator: string;
begin
  WriteLn('{');
  WriteLn('  "collector": "wsm-hwcheck-pascal",');
  WriteLn('  "environment": {');
  WriteLn('    "architecture": "', JsonEscape(ReadFirstLine(ProcRoot + '/sys/kernel/arch')), '",');
  WriteLn('    "kernel_release": "', JsonEscape(ReadFirstLine(ProcRoot + '/sys/kernel/osrelease')), '"');
  WriteLn('  },');
  WriteLn('  "pci": [');
  Separator := '';
  for Index := 0 to DeviceCount - 1 do
  begin
    WriteLn(Separator, '    {');
    WriteLn('      "address": "', JsonEscape(Devices[Index].Address), '",');
    WriteLn('      "vendor": "', JsonEscape(Devices[Index].Vendor), '",');
    WriteLn('      "device": "', JsonEscape(Devices[Index].Device), '",');
    WriteLn('      "class": "', JsonEscape(Devices[Index].ClassCode), '",');
    WriteLn('      "driver": {');
    if Devices[Index].Driver = '' then
      WriteLn('        "status": "none-known"')
    else
    begin
      if Devices[Index].Module = '' then
      begin
        WriteLn('        "status": "bound",');
        WriteLn('        "bound_driver": "', JsonEscape(Devices[Index].Driver), '"');
      end
      else
      begin
        WriteLn('        "status": "bound",');
        WriteLn('        "bound_driver": "', JsonEscape(Devices[Index].Driver), '",');
        WriteLn('        "module": "', JsonEscape(Devices[Index].Module), '",');
        WriteLn('        "module_loaded": true');
      end;
    end;
    WriteLn('      }');
    Write('    }');
    Separator := ',' + LineEnding;
  end;
  if DeviceCount > 0 then
    WriteLn;
  WriteLn('  ],');
  WriteLn('  "evidence_level": "read-only sysfs; no MMIO, no module load, no write"');
  WriteLn('}');
end;

begin
  if ParamCount > 0 then
  begin
    if (ParamStr(1) = '--help') or (ParamStr(1) = '-h') then
    begin
      WriteLn('wsm-hwcheck-pascal — read-only PCI identity evidence (first FPC slice)');
      WriteLn('usage: wsm-hwcheck-pascal');
      Halt(0);
    end;
    WriteLn(StdErr, 'wsm-hwcheck-pascal: невідомий аргумент: ', ParamStr(1));
    Halt(2);
  end;
  ScanPciDevices;
  EmitReport;
end.
