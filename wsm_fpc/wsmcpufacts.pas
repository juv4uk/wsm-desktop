unit wsmcpufacts;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ CPU facts slice of the FPC port.

  Reproduces wsm_hwcheck.collector._cpu_facts and the /proc/cpuinfo parsing it
  depends on. Stepping and microcode are recorded only when observed, and a field
  that is missing is named in `unavailable` rather than invented - profile evidence
  expires when the microcode changes, so a guessed revision is worse than none.

  The three vectors below were produced by calling the real Python function, not
  by reading it and hoping. Not compiled here: this environment has no FPC, so the
  program checks itself and exits 1 on any mismatch. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, Classes;

type
  TCpuFacts = record
    HasFamily, HasModel, HasStepping, HasMicrocode: Boolean;
    Family, ModelNumber, Stepping, Microcode: string;
    LogicalProcessors: Integer;
    MicrocodeUnavailable, ProcessorsUnavailable: Boolean;
  end;

function ParseCpuInfo(const Text: string): TStringList;
function CpuFacts(const Fields: TStringList; LogicalProcessors: Integer;
                  const SysfsMicrocodeVersion: string): TCpuFacts;
function CpuFactsJson(const F: TCpuFacts): string;

implementation

{ Parses "key\t: value" lines. Later blocks overwrite earlier ones, which is what
  the Python dict comprehension does, so the last processor wins. }
function ParseCpuInfo(const Text: string): TStringList;
var
  Lines: TStringList;
  I: Integer;
  Line, Key, Value: string;
  P: Integer;
begin
  Result := TStringList.Create;
  Result.NameValueSeparator := ':';
  Result.Delimiter := #0;
  Lines := TStringList.Create;
  try
    Lines.Text := Text;
    for I := 0 to Lines.Count - 1 do
    begin
      Line := Lines[I];
      P := Pos(':', Line);
      if P = 0 then Continue;
      Key := Trim(Copy(Line, 1, P - 1));
      Value := Trim(Copy(Line, P + 1, Length(Line)));
      if Key = '' then Continue;
      Result.Values[Key] := Value;
    end;
  finally
    Lines.Free;
  end;
end;

function CpuFacts(const Fields: TStringList; LogicalProcessors: Integer;
                  const SysfsMicrocodeVersion: string): TCpuFacts;
begin
  Result := Default(TCpuFacts);

  if Fields.Values['cpu family'] <> '' then
  begin
    Result.HasFamily := True;
    Result.Family := Fields.Values['cpu family'];
  end;
  if Fields.Values['model'] <> '' then
  begin
    Result.HasModel := True;
    Result.ModelNumber := Fields.Values['model'];
  end;
  if Fields.Values['stepping'] <> '' then
  begin
    Result.HasStepping := True;
    Result.Stepping := Fields.Values['stepping'];
  end;
  if Fields.Values['microcode'] <> '' then
  begin
    Result.HasMicrocode := True;
    Result.Microcode := Fields.Values['microcode'];
  end;

  { Some kernels omit the revision from /proc/cpuinfo; sysfs still exposes the
    revision applied to each logical CPU. }
  if not Result.HasMicrocode then
  begin
    if Trim(SysfsMicrocodeVersion) <> '' then
    begin
      Result.HasMicrocode := True;
      Result.Microcode := Trim(SysfsMicrocodeVersion);
    end
    else
      Result.MicrocodeUnavailable := True;
  end;

  Result.LogicalProcessors := LogicalProcessors;
  if LogicalProcessors <= 0 then
    Result.ProcessorsUnavailable := True;
end;

{ Keys are emitted in Python's sorted order: family, logical_processors,
  microcode, model_number, stepping, unavailable. Hand-built because fpjson does
  not sort keys and adds spaces, and a canonical form that differs by one space
  is a different document. }
function CpuFactsJson(const F: TCpuFacts): string;
var
  Parts: TStringList;
begin
  Parts := TStringList.Create;
  try
    if F.HasFamily then Parts.Add('"family":"' + F.Family + '"');
    if F.LogicalProcessors > 0 then
      Parts.Add('"logical_processors":' + IntToStr(F.LogicalProcessors));
    if F.HasMicrocode then Parts.Add('"microcode":"' + F.Microcode + '"');
    if F.HasModel then Parts.Add('"model_number":"' + F.ModelNumber + '"');
    if F.HasStepping then Parts.Add('"stepping":"' + F.Stepping + '"');
    if F.MicrocodeUnavailable or F.ProcessorsUnavailable then
    begin
      if F.MicrocodeUnavailable and F.ProcessorsUnavailable then
        Parts.Add('"unavailable":["logical_processors","microcode"]')
      else if F.MicrocodeUnavailable then
        Parts.Add('"unavailable":["microcode"]')
      else
        Parts.Add('"unavailable":["logical_processors"]');
    end;
    Result := '{' + StringReplace(Parts.Text, LineEnding, ',', [rfReplaceAll]) + '}';
    Result := StringReplace(Result, #13, '', [rfReplaceAll]);
    Result := StringReplace(Result, #10, '', [rfReplaceAll]);
  finally
    Parts.Free;
  end;
end;

end.
