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

end.
