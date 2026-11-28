// SPDX-License-Identifier: LicenseRef-Volnist
program wsm_cpu_isa;

{$mode objfpc}{$H+}

uses
  Classes, SysUtils, fpjson, jsonparser, wsm_cpu_isa_core;

procedure PrintHelp;
begin
  WriteLn('wsm-cpu-isa ', WSM_CPU_ISA_VERSION,
    ' — conservative x86-64 ISA evidence from all logical processors');
  WriteLn('Usage: wsm-cpu-isa [--compact] [--cpuinfo PATH] [--architecture NAME] [--report PATH]');
  WriteLn('       wsm-cpu-isa --version');
  WriteLn;
  WriteLn('Reads /proc/cpuinfo and emits the common x86-64 psABI feature levels.');
  WriteLn('The result is the intersection across every processor block, not CPU 0.');
  WriteLn('Read-only: no external commands, network access or device writes.');
  WriteLn('--cpuinfo and --architecture allow deterministic fixture testing.');
  WriteLn('--report optionally cross-checks the running architecture against a WSM report.');
end;


procedure AddReportCrossCheck(Evidence: TJSONObject;
  const ReportPath, Architecture: string);
var
  ReportText: TStringList;
  Parser: TJSONParser;
  Parsed: TJSONData;
  Root, CrossCheck, Environment: TJSONObject;
  EnvironmentData, WarningsData: TJSONData;
  ReportArchitecture: string;
begin
  ReportText := TStringList.Create;
  Parser := nil;
  Parsed := nil;
  Root := nil;
  CrossCheck := nil;
  try
    try
      ReportText.LoadFromFile(ReportPath);
    except
      on E: Exception do
        raise Exception.Create('cannot read report ' + ReportPath + ': ' + E.Message);
    end;

    try
      Parser := TJSONParser.Create(ReportText.Text);
      Parsed := Parser.Parse;
      if not (Parsed is TJSONObject) then
        raise Exception.Create('report root is not a JSON object');
      Root := TJSONObject(Parsed);
      Parsed := nil;

      ReportArchitecture := '';
      EnvironmentData := Root.Find('environment');
      if (EnvironmentData <> nil) and (EnvironmentData is TJSONObject) then
        ReportArchitecture := TJSONObject(EnvironmentData).Get('architecture', '');

      WarningsData := Evidence.Find('warnings');
      if (ReportArchitecture <> '') and (ReportArchitecture <> Architecture) and
         (WarningsData is TJSONArray) then
        TJSONArray(WarningsData).Add(
          'report architecture ' + QuotedStr(ReportArchitecture) +
          ' differs from the running machine ' + QuotedStr(Architecture) +
          '; the report describes another host');

      CrossCheck := TJSONObject.Create;
      if Root.IndexOfName('report_id') >= 0 then
        CrossCheck.Add('report_id', Root.Get('report_id', ''))
      else
        CrossCheck.Add('report_id', GetJSON('null'));

      if ReportArchitecture <> '' then
        CrossCheck.Add('report_architecture', ReportArchitecture)
      else
        CrossCheck.Add('report_architecture', GetJSON('null'));

      if Root.IndexOfName('schema_version') >= 0 then
        CrossCheck.Add('report_schema_version', Root.Get('schema_version', ''))
      else
        CrossCheck.Add('report_schema_version', GetJSON('null'));

      Evidence.Add('cross_check', CrossCheck);
      CrossCheck := nil;
    except
      on E: Exception do
        raise Exception.Create('cannot read report ' + ReportPath + ': ' + E.Message);
    end;
  finally
    CrossCheck.Free;
    Root.Free;
    Parsed.Free;
    Parser.Free;
    ReportText.Free;
  end;
end;

procedure Fail(const MessageText: string; ExitCode: Integer);
begin
  WriteLn(ErrOutput, 'wsm-cpu-isa: ', MessageText);
  Halt(ExitCode);
end;

var
  CpuInfoPath, Architecture, ReportPath, Argument, OutputText: string;
  Compact: Boolean;
  Index: Integer;
  Evidence: TJSONObject;
begin
  CpuInfoPath := '/proc/cpuinfo';
  Architecture := '';
  ReportPath := '';
  Compact := False;

  Index := 1;
  while Index <= ParamCount do
  begin
    Argument := ParamStr(Index);
    if (Argument = '--help') or (Argument = '-h') then
    begin
      PrintHelp;
      Halt(0);
    end
    else if Argument = '--version' then
    begin
      WriteLn('wsm-cpu-isa ', WSM_CPU_ISA_VERSION);
      Halt(0);
    end
    else if Argument = '--compact' then
      Compact := True
    else if (Argument = '--cpuinfo') or (Argument = '--architecture') or
            (Argument = '--report') then
    begin
      Inc(Index);
      if Index > ParamCount then
        Fail('argument requires a value: ' + Argument, 2);
      if Trim(ParamStr(Index)) = '' then
        Fail('argument requires a non-empty value: ' + Argument, 2);
      if Argument = '--cpuinfo' then
        CpuInfoPath := ParamStr(Index)
      else if Argument = '--report' then
        ReportPath := ParamStr(Index)
      else
        Architecture := ParamStr(Index);
    end
    else
      Fail('unknown argument: ' + Argument, 2);
    Inc(Index);
  end;

  if Architecture = '' then
    Architecture := DetectArchitecture;

  try
    Evidence := BuildEvidence(CpuInfoPath, Architecture);
    try
      if ReportPath <> '' then
        AddReportCrossCheck(Evidence, ReportPath, Architecture);
      if Compact then
        OutputText := Evidence.AsJSON
      else
        OutputText := Evidence.FormatJSON;
    finally
      Evidence.Free;
    end;
    Write(OutputText, LineEnding);
  except
    on E: EIsaError do
      Fail(E.Message, 2);
    on E: Exception do
      Fail(E.ClassName + ': ' + E.Message, 2);
  end;
end.
