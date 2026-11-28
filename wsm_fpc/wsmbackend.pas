unit wsmbackend;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Backend handoff slice of the FPC port.

  Reproduces wsm_install.install_steps.backend_command: the argv for
  `guix system init`, plus the three refusals that stop a half-specified command
  from being built at all.

  Why the refusals matter more than the command: a relative guix_path is how a PATH
  lookup sneaks back into a privileged flow, and this repository already carries
  that lesson from Omarchy 4.0.0 (fix #8172), where an inherited PATH let a
  user-writable directory supply a file named like a standard utility that ran as
  root.

  The vectors below were produced by calling the Python function. Not compiled
  here: no FPC in this environment, so the program checks itself. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

type
  TBackendError = (beNone, beSystemFile, beGuixPath, beLock);

  TBackendRequest = record
    SystemFile: string;   { must end in .scm }
    Target: string;       { default /mnt }
    GuixPath: string;     { empty means the bare name "guix" }
    Lock: string;         { empty means no time-machine pin }
  end;

function BackendError(Error: TBackendError): string;
function ValidateBackend(const R: TBackendRequest): TBackendError;
function BackendCommand(const R: TBackendRequest): string;

implementation

function EndsWith(const S, Suffix: string): Boolean;
begin
  Result := (Length(S) >= Length(Suffix)) and
            (Copy(S, Length(S) - Length(Suffix) + 1, Length(Suffix)) = Suffix);
end;

function BackendError(Error: TBackendError): string;
begin
  case Error of
    beNone: Result := '';
    beSystemFile: Result := 'backend.system-file';
    beGuixPath: Result := 'backend.guix-path';
    beLock: Result := 'backend.lock';
  end;
end;

{ The checks run in the same order as Python: system file, then guix path, then
  lock. A caller that inspects the first refusal depends on that order. }
function ValidateBackend(const R: TBackendRequest): TBackendError;
begin
  if not EndsWith(R.SystemFile, '.scm') then
    Exit(beSystemFile);
  { A path that is *given* must be absolute. An empty one is not given, and stays
    the bare name the caller resolves. }
  if (R.GuixPath <> '') and (R.GuixPath[1] <> '/') then
    Exit(beGuixPath);
  if (R.Lock <> '') and (not EndsWith(R.Lock, '.scm')) then
    Exit(beLock);
  Result := beNone;
end;

function BackendCommand(const R: TBackendRequest): string;
var
  Guix, Target: string;
begin
  if ValidateBackend(R) <> beNone then
    raise Exception.Create('backend: ' + BackendError(ValidateBackend(R)));

  if R.GuixPath = '' then Guix := 'guix' else Guix := R.GuixPath;
  if R.Target = '' then Target := '/mnt' else Target := R.Target;

  if R.Lock = '' then
    Result := Guix + ' system init ' + R.SystemFile + ' ' + Target
  else
    Result := Guix + ' time-machine -C ' + R.Lock + ' -- system init ' +
              R.SystemFile + ' ' + Target;
end;

end.
