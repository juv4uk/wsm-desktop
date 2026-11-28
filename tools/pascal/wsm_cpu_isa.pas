// SPDX-License-Identifier: LicenseRef-Volnist
program wsm_cpu_isa;

{$mode objfpc}{$H+}

uses
  SysUtils, fpjson, wsm_cpu_isa_core;

procedure PrintHelp;
begin
  WriteLn('wsm-cpu-isa ', WSM_CPU_ISA_VERSION,
    ' — conservative x86-64 ISA evidence from all logical processors');
  WriteLn('Usage: wsm-cpu-isa [--compact] [--cpuinfo PATH] [--architecture NAME]');
  WriteLn('       wsm-cpu-isa --version');
  WriteLn;
  WriteLn('Reads /proc/cpuinfo and emits the common x86-64 psABI feature levels.');
  WriteLn('The result is the intersection across every processor block, not CPU 0.');
  WriteLn('Read-only: no external commands, network access or device writes.');
  WriteLn('--cpuinfo and --architecture allow deterministic fixture testing.');
end;

procedure Fail(const MessageText: string; ExitCode: Integer);
begin
  WriteLn(ErrOutput, 'wsm-cpu-isa: ', MessageText);
  Halt(ExitCode);
end;

var
  CpuInfoPath, Architecture, Argument, OutputText: string;
  Compact: Boolean;
  Index: Integer;
  Evidence: TJSONObject;
begin
  CpuInfoPath := '/proc/cpuinfo';
  Architecture := '';
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
    else if (Argument = '--cpuinfo') or (Argument = '--architecture') then
    begin
      Inc(Index);
      if Index > ParamCount then
        Fail('argument requires a value: ' + Argument, 2);
      if Trim(ParamStr(Index)) = '' then
        Fail('argument requires a non-empty value: ' + Argument, 2);
      if Argument = '--cpuinfo' then
        CpuInfoPath := ParamStr(Index)
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
