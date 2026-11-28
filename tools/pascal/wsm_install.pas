{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-install, FPC edition: the frontend that runs the five readers in order.

  This unit EXECUTES, and that is the whole difference from the others. The
  planner, the classifier and the profile reader are deliberately incapable of
  running anything; this one exists to sequence them. What it may run is fixed
  and named: only the sibling binaries listed below. It never builds a command
  from user input, never passes a shell, and never invokes sgdisk - the plan is
  printed for a human, not applied.

  Order matters and encodes the safety rule:
    1. preflight  - if it fails, nothing else runs. There is no point reading
                    hardware on a machine that cannot be installed to.
    2. hwcheck    - only when no report was supplied; a supplied report is
                    preferred over a fresh probe, because the plan must describe
                    the machine the operator actually inspected.
    3. classify   - the diagnostic summary of that report.
    4. partition  - the layout, which refuses without an acknowledgement.

  An `incomplete' preflight is not a pass: it stops here too, and says why.
}
program wsm_install;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, Process;

const
  ExitOk = 0;
  ExitPreflightFail = 1;
  ExitIncomplete = 6;
  ExitUsage = 2;
  ExitTool = 7;

type
  TStep = record
    Name: string;
    Code: Integer;
    Output: string;
  end;

var
  Steps: array of TStep;
  StepCount: Integer = 0;

function SiblingPath(const Name: string): string;
begin
  { Resolve next to this binary so a relocated install still finds its tools. }
  Result := IncludeTrailingPathDelimiter(ExtractFileDir(ExpandFileName(ParamStr(0)))) + Name;
  if not FileExists(Result) then
    Result := Name;
end;

function RunToolCode(const Name: string; const Args: array of string; out Output: string): Integer;
var
  P: TProcess;
  I: Integer;
  Bytes: TStringList;
begin
  P := TProcess.Create(nil);
  Bytes := TStringList.Create;
  try
    P.Executable := SiblingPath(Name);
    for I := Low(Args) to High(Args) do
      P.Parameters.Add(Args[I]);
    P.Options := [poUsePipes, poStderrToOutPut, poWaitOnExit];
    P.Execute;
    Bytes.LoadFromStream(P.Output);
    Output := Trim(Bytes.Text);
    Result := P.ExitStatus;
  finally
    Bytes.Free;
    P.Free;
  end;
end;

procedure Record_(const Name: string; Code: Integer; const Output: string);
begin
  SetLength(Steps, StepCount + 1);
  Steps[StepCount].Name := Name;
  Steps[StepCount].Code := Code;
  Steps[StepCount].Output := Output;
  Inc(StepCount);
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
      #9:  Result := Result + '\t';
      #10: Result := Result + '\n';
      #13: Result := Result + '\r';
    else
      if C < #32 then
        Result := Result + ' '
      else
        Result := Result + C;
    end;
  end;
end;

var
  ReportPath, MountPoint, SystemFile, DiskPath, Firmware, Ack: string;
  SizeBytes: string;
  I: Integer;
  Code: Integer;
  Output: string;
  PreflightCode: Integer;
  Overall: string;
begin
  ReportPath := '';
  MountPoint := '/mnt';
  SystemFile := 'systems/desktop.scm';
  DiskPath := '';
  Firmware := '';
  Ack := '';
  SizeBytes := '';

  I := 1;
  while I <= ParamCount do
  begin
    if (ParamStr(I) = '--report') and (I < ParamCount) then
    begin ReportPath := ParamStr(I + 1); Inc(I, 2); end
    else if (ParamStr(I) = '--mount-point') and (I < ParamCount) then
    begin MountPoint := ParamStr(I + 1); Inc(I, 2); end
    else if (ParamStr(I) = '--system-file') and (I < ParamCount) then
    begin SystemFile := ParamStr(I + 1); Inc(I, 2); end
    else if (ParamStr(I) = '--disk') and (I < ParamCount) then
    begin DiskPath := ParamStr(I + 1); Inc(I, 2); end
    else if (ParamStr(I) = '--size') and (I < ParamCount) then
    begin SizeBytes := ParamStr(I + 1); Inc(I, 2); end
    else if (ParamStr(I) = '--firmware') and (I < ParamCount) then
    begin Firmware := ParamStr(I + 1); Inc(I, 2); end
    else if (ParamStr(I) = '--ack') and (I < ParamCount) then
    begin Ack := ParamStr(I + 1); Inc(I, 2); end
    else
    begin
      WriteLn(StdErr, 'usage: wsm-install [--report FILE] [--mount-point DIR] ',
                      '[--system-file FILE] [--disk DEV --size BYTES ',
                      '--firmware uefi|bios --ack DEV]');
      Halt(ExitUsage);
    end;
  end;

  { 1. Preflight first: reading hardware on a machine that cannot be installed
       to wastes the operator's time and looks like progress. }
  PreflightCode := RunToolCode('wsm-preflight',
    ['--mount-point', MountPoint, '--system-file', SystemFile,
     '--report', ReportPath], Output);
  Record_('preflight', PreflightCode, Output);

  if PreflightCode = ExitPreflightFail then
  begin
    WriteLn(StdErr, 'wsm-install: preflight failed; nothing else was run');
    WriteLn(Output);
    Halt(ExitPreflightFail);
  end;
  if PreflightCode = ExitIncomplete then
  begin
    WriteLn(StdErr, 'wsm-install: preflight is incomplete, which is not a pass');
    WriteLn(Output);
    Halt(ExitIncomplete);
  end;

  { 2. A supplied report wins over a fresh probe. }
  if ReportPath = '' then
  begin
    Code := RunToolCode('wsm-hwcheck', [], Output);
    Record_('hwcheck', Code, Output);
    if Code <> 0 then
    begin
      WriteLn(StdErr, 'wsm-install: hardware collection failed');
      Halt(ExitTool);
    end;
  end;

  { 3. Classification is diagnostic only; a failure here does not stop a plan,
       but it is recorded so the operator sees it. }
  if ReportPath <> '' then
  begin
    Code := RunToolCode('wsm-classify', [ReportPath], Output);
    Record_('classify', Code, Output);
  end;

  { 4. The layout. The planner refuses without an acknowledgement naming the
       device, so an operator who typed nothing gets a refusal, not a plan. }
  if DiskPath <> '' then
  begin
    Code := RunToolCode('wsm-partition',
      ['--disk', DiskPath, '--size', SizeBytes, '--firmware', Firmware, '--ack', Ack],
      Output);
    Record_('partition', Code, Output);
  end;

  Overall := 'ok';
  for I := 0 to StepCount - 1 do
    if Steps[I].Code <> 0 then
      Overall := 'refused';

  Write('{"schema":"wsm-install-plan/1","overall":"', Overall, '"');
  Write(',"applied":false');
  Write(',"steps":[');
  for I := 0 to StepCount - 1 do
  begin
    if I > 0 then Write(',');
    Write('{"step":"', JsonEscape(Steps[I].Name), '"');
    Write(',"exit":', Steps[I].Code);
    Write(',"output":"', JsonEscape(Steps[I].Output), '"}');
  end;
  Write('],"note":"Nothing was applied. The layout is a proposal for review."');
  WriteLn('}');

  if Overall <> 'ok' then
    Halt(ExitTool);
end.
