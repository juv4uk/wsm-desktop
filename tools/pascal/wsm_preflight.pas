{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-preflight, FPC edition: can this machine install WSM, before anything is
  touched.

  Criteria are the same set the Python preflight reports, in the same spirit:
  every one of them is a reason the install would fail *after* it started
  writing, which is the worst possible moment to discover it.

  The verdict rule is the part worth copying exactly:

      any `fail'        -> fail
      else any `not-run' -> incomplete
      else               -> pass

  `incomplete' is not a pass. A check that did not run proves nothing, and a
  frontend that renders it green would be lying about the one thing it exists
  to report.

  It reads only: PATH, /proc/mounts, /proc/cpuinfo and file existence. It never
  writes and never executes anything.
}
program wsm_preflight;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, BaseUnix;

type
  TCriterion = record
    Id: string;
    Status: string;
    Detail: string;
  end;

const
  Schema = 'wsm-preflight/1';

var
  Criteria: array of TCriterion;
  Count: Integer = 0;

procedure Add(const Id, Status, Detail: string);
begin
  SetLength(Criteria, Count + 1);
  Criteria[Count].Id := Id;
  Criteria[Count].Status := Status;
  Criteria[Count].Detail := Detail;
  Inc(Count);
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

{ A bare name is found on PATH; an absolute path is checked directly. The
  install plan calls absolute paths inside the image, so both forms matter. }
function Which(const Program_: string): string;
var
  SearchPath, Item: string;
  Rest: string;
  Candidate: string;
  Info: TSearchRec;
begin
  Result := '';
  if (Program_ = '') then
    Exit;
  if Program_[1] = '/' then
  begin
    if FileExists(Program_) and (FpAccess(Program_, X_OK) = 0) then
      Result := Program_;
    Exit;
  end;

  SearchPath := GetEnvironmentVariable('PATH');
  Rest := SearchPath;
  while Rest <> '' do
  begin
    if Pos(':', Rest) > 0 then
    begin
      Item := Copy(Rest, 1, Pos(':', Rest) - 1);
      Rest := Copy(Rest, Pos(':', Rest) + 1, Length(Rest));
    end
    else
    begin
      Item := Rest;
      Rest := '';
    end;
    if Item = '' then
      Continue;
    Candidate := IncludeTrailingPathDelimiter(Item) + Program_;
    if FileExists(Candidate) and (FpAccess(Candidate, X_OK) = 0) then
    begin
      Result := Candidate;
      Exit;
    end;
  end;
  { Silence the unused-variable warning without changing behaviour. }
  Info.Name := '';
end;

procedure CheckTool(const Id, Program_, Package: string);
begin
  if Which(Program_) = '' then
    Add(Id, 'fail', Program_ + ' (' + Package + ' missing) - the install cannot proceed')
  else
    Add(Id, 'pass', Program_ + ' is available');
end;

function IsMountPoint(const Path: string): Boolean;
var
  Mounts: TStringList;
  I: Integer;
  Line, Target: string;
begin
  Result := False;
  Mounts := TStringList.Create;
  try
    try
      Mounts.LoadFromFile('/proc/mounts');
    except
      Exit;
    end;
    for I := 0 to Mounts.Count - 1 do
    begin
      Line := Mounts[I];
      { /proc/mounts: device target fstype options dump pass }
      if Pos(' ', Line) = 0 then
        Continue;
      Line := Trim(Copy(Line, Pos(' ', Line) + 1, Length(Line)));
      if Pos(' ', Line) = 0 then
        Continue;
      Target := Copy(Line, 1, Pos(' ', Line) - 1);
      if Target = Path then
        Exit(True);
    end;
  finally
    Mounts.Free;
  end;
end;

procedure CheckMountPoint(const Path: string);
begin
  { An already-used mount point hides the new system under an old one. }
  if not DirectoryExists(Path) then
    Add('mount-point', 'fail', Path + ' does not exist')
  else if IsMountPoint(Path) then
    Add('mount-point', 'fail',
        Path + ' is already a mount point; the new system would hide under it')
  else
    Add('mount-point', 'pass', Path + ' is an ordinary directory');
end;

procedure CheckSystemFile(const Path: string);
begin
  if not FileExists(Path) then
    Add('system-file', 'fail', Path + ' does not exist; there is nothing to install')
  else
    Add('system-file', 'pass', Path + ' is present');
end;

procedure CheckReport(const Path: string);
begin
  if Path = '' then
    Add('report', 'not-run',
        'no hardware report was supplied; the plan is not tied to this machine')
  else if not FileExists(Path) then
    Add('report', 'fail', Path + ' was supplied but does not exist')
  else
    Add('report', 'pass', Path + ' is present');
end;

procedure CheckIsa;
var
  CpuInfo: TStringList;
  I: Integer;
  Line: string;
begin
  CpuInfo := TStringList.Create;
  try
    try
      CpuInfo.LoadFromFile('/proc/cpuinfo');
    except
      Add('isa', 'not-run', '/proc/cpuinfo is not readable; the instruction set is unverified');
      Exit;
    end;
    for I := 0 to CpuInfo.Count - 1 do
    begin
      Line := CpuInfo[I];
      if (Pos('lm', Line) > 0) and (Pos('flags', Line) > 0) then
      begin
        Add('isa', 'pass', 'x86_64 long mode is reported by /proc/cpuinfo');
        Exit;
      end;
    end;
    Add('isa', 'not-run',
        'no long-mode flag was found; this reader does not decide 32-bit support');
  finally
    CpuInfo.Free;
  end;
end;

var
  MountPoint, SystemFile, ReportPath: string;
  I: Integer;
  Overall: string;
  AnyFail, AnyNotRun: Boolean;
begin
  MountPoint := '/mnt';
  SystemFile := 'systems/desktop.scm';
  ReportPath := '';

  I := 1;
  while I <= ParamCount do
  begin
    if (ParamStr(I) = '--mount-point') and (I < ParamCount) then
    begin
      MountPoint := ParamStr(I + 1); Inc(I, 2);
    end
    else if (ParamStr(I) = '--system-file') and (I < ParamCount) then
    begin
      SystemFile := ParamStr(I + 1); Inc(I, 2);
    end
    else if (ParamStr(I) = '--report') and (I < ParamCount) then
    begin
      ReportPath := ParamStr(I + 1); Inc(I, 2);
    end
    else
    begin
      WriteLn(StdErr, 'usage: wsm-preflight [--mount-point DIR] [--system-file FILE] [--report FILE]');
      Halt(2);
    end;
  end;

  CheckTool('tools', 'sgdisk', 'gptfdisk');
  CheckTool('guix', 'guix', 'guix');

  if FpGeteuid <> 0 then
    Add('root', 'fail', 'not running as root; formatting and mounting will fail')
  else
    Add('root', 'pass', 'running as root');

  CheckMountPoint(MountPoint);
  CheckSystemFile(SystemFile);
  CheckReport(ReportPath);
  CheckIsa;

  AnyFail := False;
  AnyNotRun := False;
  for I := 0 to Count - 1 do
  begin
    if Criteria[I].Status = 'fail' then AnyFail := True;
    if Criteria[I].Status = 'not-run' then AnyNotRun := True;
  end;

  if AnyFail then
    Overall := 'fail'
  else if AnyNotRun then
    Overall := 'incomplete'
  else
    Overall := 'pass';

  Write('{"schema":"', Schema, '","overall":"', Overall, '","criteria":[');
  for I := 0 to Count - 1 do
  begin
    if I > 0 then Write(',');
    Write('{"id":"', JsonEscape(Criteria[I].Id), '"');
    Write(',"status":"', JsonEscape(Criteria[I].Status), '"');
    Write(',"detail":"', JsonEscape(Criteria[I].Detail), '"}');
  end;
  Write('],"note":"incomplete is not a pass: a check that did not run proves nothing"');
  WriteLn('}');

  if Overall = 'fail' then
    Halt(1)
  else if Overall = 'incomplete' then
    Halt(6);
end.
