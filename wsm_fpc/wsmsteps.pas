unit wsmsteps;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Step naming slice of the FPC port.

  Reproduces wsm_install.install_steps.device_for and the argv rules that
  plan_digest already relies on.

  device_for is small and decides something expensive: /dev/sda + 1 is /dev/sda1,
  but /dev/nvme0n1 + 1 is /dev/nvme0n1p1. Getting this wrong formats the disk
  instead of the partition, which is why it is computed in one place and tested
  rather than inlined wherever it is needed.

  The vectors below were produced by calling the Python function. Not compiled
  here: no FPC in this environment, so the program checks itself. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

type
  TStepError = (seNone, seEmptyArgv, seStepType);

function DeviceFor(const Disk: string; Number: Integer): string;
function ValidateStep(const Argv: array of string; const Purpose: string): TStepError;
function StepErrorCode(Error: TStepError): string;
function Render(const Steps: array of string; const Purposes: array of string;
                const Destructive: array of Boolean;
                const Command: array of string): string;

implementation

{ The kernel appends the partition number directly unless the disk name already
  ends in a digit - nvme, mmcblk and loop devices need the "p" separator. }
function DeviceFor(const Disk: string; Number: Integer): string;
begin
  if (Disk = '') then
    raise Exception.Create('device_for: empty disk');
  if (Disk[Length(Disk)] >= '0') and (Disk[Length(Disk)] <= '9') then
    Result := Disk + 'p' + IntToStr(Number)
  else
    Result := Disk + IntToStr(Number);
end;

{ Mirrors _render_step: an empty argv or a non-string element is refused before
  anything is hashed, so a malformed plan never reaches a digest. }
function ValidateStep(const Argv: array of string; const Purpose: string): TStepError;
var
  I: Integer;
begin
  if Length(Argv) = 0 then
    Exit(seEmptyArgv);
  for I := 0 to High(Argv) do
    if Argv[I] = '' then
      Exit(seStepType);
  Result := seNone;
end;

function StepErrorCode(Error: TStepError): string;
begin
  case Error of
    seNone: Result := '';
    seEmptyArgv: Result := 'plan.command';
    seStepType: Result := 'plan.step-type';
  end;
end;

{ The human-readable plan. The first line is not decoration: the file exists to be
  read before anything runs, and every destructive step is marked in it. }
function Render(const Steps: array of string; const Purposes: array of string;
                const Destructive: array of Boolean;
                const Command: array of string): string;
var
  I: Integer;
  Marker, Joined: string;
begin
  Result := '# NOT EXECUTED - review every line before running anything' + LineEnding
          + LineEnding;
  for I := 0 to High(Steps) do
  begin
    if Destructive[I] then Marker := 'DESTRUCTIVE' else Marker := 'safe';
    Result := Result + '# [' + Marker + '] ' + Purposes[I] + LineEnding;
    Result := Result + Steps[I] + LineEnding;
    Result := Result + LineEnding;
  end;
  Result := Result + '# handoff to the backend' + LineEnding;
  { No String.Join in FPC's objfpc mode - joined by hand. }
  Joined := '';
  for I := 0 to High(Command) do
  begin
    if I > 0 then Joined := Joined + ' ';
    Joined := Joined + Command[I];
  end;
  Result := Result + Joined + LineEnding;
end;

end.
