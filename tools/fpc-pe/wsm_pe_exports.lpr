{ SPDX-License-Identifier: LicenseRef-Volnist }
{ Read-only PE header/export-table reader. No code from the image is executed. }
program wsm_pe_exports;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes;

type
  TSection = record
    VirtualAddress: LongWord;
    VirtualSize: LongWord;
    RawOffset: LongWord;
    RawSize: LongWord;
  end;

var
  Image: TMemoryStream;
  Sections: array of TSection;

procedure Fail(const Msg: string);
begin
  raise Exception.Create(Msg);
end;

function U16(Off: Int64): Word;
var
  B: array[0..1] of Byte;
begin
  if (Off < 0) or (Off + 2 > Image.Size) then Fail('u16 out of bounds');
  Image.Position := Off;
  Image.ReadBuffer(B, 2);
  Result := Word(B[0]) or (Word(B[1]) shl 8);
end;

function U32(Off: Int64): LongWord;
var
  B: array[0..3] of Byte;
begin
  if (Off < 0) or (Off + 4 > Image.Size) then Fail('u32 out of bounds');
  Image.Position := Off;
  Image.ReadBuffer(B, 4);
  Result := LongWord(B[0]) or (LongWord(B[1]) shl 8) or
            (LongWord(B[2]) shl 16) or (LongWord(B[3]) shl 24);
end;

function JsonEscape(const S: string): string;
var
  I: Integer;
  Ch: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    Ch := S[I];
    case Ch of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #8:  Result := Result + '\b';
      #9:  Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
    else
      if Ord(Ch) < 32 then
        Result := Result + '\u00' + IntToHex(Ord(Ch), 2)
      else
        Result := Result + Ch;
    end;
  end;
end;

function RvaToOffset(Rva: LongWord): Int64;
var
  I: Integer;
  Delta, Span: LongWord;
begin
  for I := 0 to High(Sections) do
  begin
    if Rva >= Sections[I].VirtualAddress then
    begin
      Delta := Rva - Sections[I].VirtualAddress;
      Span := Sections[I].VirtualSize;
      if Span = 0 then Span := Sections[I].RawSize;
      if (Delta < Span) and (Delta < Sections[I].RawSize) then
      begin
        Result := Int64(Sections[I].RawOffset) + Delta;
        if Result < Image.Size then Exit;
      end;
    end;
  end;
  Fail('rva not mapped to file data');
  Result := -1;
end;

function ReadCString(Off: Int64): string;
var
  C: Byte;
begin
  Result := '';
  if (Off < 0) or (Off >= Image.Size) then Fail('string offset out of bounds');
  while Off < Image.Size do
  begin
    Image.Position := Off;
    Image.ReadBuffer(C, 1);
    if C = 0 then Exit;
    if Length(Result) >= 4096 then Fail('string too long');
    Result := Result + Chr(C);
    Inc(Off);
  end;
  Fail('unterminated string');
end;

function JsonString(const S: string): string;
begin
  Result := '"' + JsonEscape(S) + '"';
end;

var
  Path, MachineName, Json, Name: string;
  PeOff, OptOff, DdOff, SecOff, Off: Int64;
  ExpOff, EatOff, NamesOff, OrdsOff, NameOff, FwdOff: Int64;
  Machine, Magic, NumSections, SizeOpt, Bits: Word;
  ExpRva, ExpSize, EatRva, NamesRva, OrdsRva: LongWord;
  Base, NumRva, NumFuncs, NumNames, Idx: LongWord;
  NamesByIndex: array of string;
  I: Integer;
  Rva: LongWord;
  Ordinal: QWord;
  Forwarder: string;
  First: Boolean;

begin
  if ParamCount <> 1 then
  begin
    WriteLn(StdErr, 'usage: wsm_pe_exports <pe-file>');
    Halt(2);
  end;
  Path := ParamStr(1);
  Image := TMemoryStream.Create;
  try
    try
      Image.LoadFromFile(Path);
      if Image.Size < 64 then Fail('file too small for dos header');
      if U16(0) <> $5A4D then Fail('missing MZ signature');

      PeOff := U32($3C);
      if (PeOff + 24 > Image.Size) then Fail('bad pe offset');
      if U32(PeOff) <> $00004550 then Fail('missing PE signature');
      Machine := U16(PeOff + 4);
      NumSections := U16(PeOff + 6);
      SizeOpt := U16(PeOff + 20);
      OptOff := PeOff + 24;
      if (SizeOpt < 96) or (OptOff + SizeOpt > Image.Size) then
        Fail('optional header truncated');

      Magic := U16(OptOff);
      case Magic of
        $10B: begin Bits := 32; DdOff := OptOff + 96; end;
        $20B: begin Bits := 64; DdOff := OptOff + 112; end;
      else
        Fail('unsupported optional header magic');
      end;
      if DdOff + 8 > Image.Size then Fail('data directory truncated');

      case Machine of
        $014C: MachineName := 'i386';
        $8664: MachineName := 'amd64';
        $AA64: MachineName := 'arm64';
      else
        MachineName := '0x' + IntToHex(Machine, 4);
      end;

      SetLength(Sections, NumSections);
      SecOff := OptOff + SizeOpt;
      for I := 0 to Integer(NumSections) - 1 do
      begin
        Off := SecOff + Int64(I) * 40;
        if Off + 40 > Image.Size then Fail('section table truncated');
        Sections[I].VirtualSize := U32(Off + 8);
        Sections[I].VirtualAddress := U32(Off + 12);
        Sections[I].RawSize := U32(Off + 16);
        Sections[I].RawOffset := U32(Off + 20);
      end;

      ExpRva := 0;
      ExpSize := 0;
      NumRva := U32(DdOff - 4);
      if NumRva > 0 then
      begin
        ExpRva := U32(DdOff);
        ExpSize := U32(DdOff + 4);
      end;
      NumFuncs := 0;
      if ExpRva <> 0 then
      begin
        ExpOff := RvaToOffset(ExpRva);
        if ExpOff + 40 > Image.Size then Fail('export directory truncated');
        Base := U32(ExpOff + 16);
        NumFuncs := U32(ExpOff + 20);
        NumNames := U32(ExpOff + 24);
        EatRva := U32(ExpOff + 28);
        NamesRva := U32(ExpOff + 32);
        OrdsRva := U32(ExpOff + 36);
        if (NumFuncs = 0) or (NumFuncs > 65536) then Fail('bad export function count');
        if NumNames > NumFuncs then Fail('bad export name count');

        EatOff := RvaToOffset(EatRva);
        if EatOff + Int64(NumFuncs) * 4 > Image.Size then Fail('export address table truncated');
        SetLength(NamesByIndex, NumFuncs);
        for I := 0 to Integer(NumFuncs) - 1 do NamesByIndex[I] := '';

        if NumNames > 0 then
        begin
          NamesOff := RvaToOffset(NamesRva);
          OrdsOff := RvaToOffset(OrdsRva);
          if (NamesOff + Int64(NumNames) * 4 > Image.Size) or
             (OrdsOff + Int64(NumNames) * 2 > Image.Size) then
            Fail('export name tables truncated');
          for I := 0 to Integer(NumNames) - 1 do
          begin
            NameOff := RvaToOffset(U32(NamesOff + Int64(I) * 4));
            Name := ReadCString(NameOff);
            Idx := U16(OrdsOff + Int64(I) * 2);
            if Idx >= NumFuncs then Fail('name ordinal index out of range');
            NamesByIndex[Idx] := Name;
          end;
        end;
      end;

      Json := '{"format":"pe","machine":' + JsonString(MachineName) +
              ',"bits":' + IntToStr(Bits) +
              ',"export_count":' + IntToStr(NumFuncs) + ',"exports":[';
      First := True;
      for I := 0 to Integer(NumFuncs) - 1 do
      begin
        Rva := U32(EatOff + Int64(I) * 4);
        Forwarder := '';
        if (Rva >= ExpRva) and (Rva < ExpRva + ExpSize) then
        begin
          FwdOff := RvaToOffset(Rva);
          Forwarder := ReadCString(FwdOff);
        end;
        Ordinal := QWord(Base) + QWord(I);
        if not First then Json := Json + ',';
        First := False;
        Json := Json + '{"ordinal":' + IntToStr(Int64(Ordinal)) +
                ',"name":';
        if NamesByIndex[I] = '' then
          Json := Json + 'null'
        else
          Json := Json + JsonString(NamesByIndex[I]);
        Json := Json + ',"rva":' + IntToStr(Int64(Rva)) + ',"forwarder":';
        if Forwarder = '' then
          Json := Json + 'null'
        else
          Json := Json + JsonString(Forwarder);
        Json := Json + '}';
      end;
      Json := Json + ']}';
      WriteLn(Json);
    except
      on E: Exception do
      begin
        WriteLn(StdErr, 'wsm_pe_exports: ' + E.Message);
        Halt(1);
      end;
    end;
  finally
    Image.Free;
  end;
end.
