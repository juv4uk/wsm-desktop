// SPDX-License-Identifier: LicenseRef-Volnist
program wsm_hwcheck;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, fpjson, wsm_hwcheck_core;

procedure PrintHelp;
begin
  WriteLn('wsm-hwcheck ', WSM_FPC_VERSION, ' — native Free Pascal hardware evidence collector');
  WriteLn('usage: wsm-hwcheck [--output PATH] [--compact] [--sysfs-root PATH] [--proc-root PATH]');
  WriteLn('       wsm-hwcheck --version');
  WriteLn;
  WriteLn('Reads local Linux sysfs/procfs. No network, module loads, firmware updates,');
  WriteLn('partition changes, or writes to target devices. JSON is written to stdout');
  WriteLn('unless --output explicitly names a report file.');
end;

procedure Fail(const MessageText: string; ExitCode: Integer);
begin
  WriteLn(ErrOutput, 'wsm-hwcheck: ', MessageText);
  Halt(ExitCode);
end;

var
  SysfsRoot, ProcRoot, OutputPath, Argument, OutputText: string;
  Compact: Boolean;
  Index: Integer;
  Report: TJSONObject;
  Stream: TFileStream;
begin
  SysfsRoot := '/sys';
  ProcRoot := '/proc';
  OutputPath := '';
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
      WriteLn('wsm-hwcheck ', WSM_FPC_VERSION);
      Halt(0);
    end
    else if Argument = '--compact' then
      Compact := True
    else if Argument = '--no-runtime-diagnostics' then
    begin
      { Runtime diagnostics are deliberately not implemented in this version. }
    end
    else if (Argument = '--output') or (Argument = '--sysfs-root') or
            (Argument = '--proc-root') then
    begin
      Inc(Index);
      if Index > ParamCount then
        Fail('argument requires a path: ' + Argument, 2);
      if ParamStr(Index) = '' then
        Fail('argument requires a non-empty path: ' + Argument, 2);
      if Argument = '--output' then OutputPath := ParamStr(Index)
      else if Argument = '--sysfs-root' then SysfsRoot := ParamStr(Index)
      else ProcRoot := ParamStr(Index);
    end
    else
      Fail('unknown argument: ' + Argument, 2);
    Inc(Index);
  end;

  try
    Report := CollectReport(SysfsRoot, ProcRoot);
    try
      if Compact then
        OutputText := Report.AsJSON
      else
        OutputText := Report.FormatJSON;
    finally
      Report.Free;
    end;
    OutputText := OutputText + LineEnding;

    if OutputPath = '' then
      Write(OutputText)
    else
    begin
      Stream := TFileStream.Create(OutputPath, fmCreate);
      try
        if Length(OutputText) > 0 then
          Stream.WriteBuffer(OutputText[1], Length(OutputText));
      finally
        Stream.Free;
      end;
    end;
  except
    on E: Exception do
      Fail(E.ClassName + ': ' + E.Message, 2);
  end;
end.
