unit wsmguixargv;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Deployment argv slice of the FPC port.

  Reproduces two functions from wsm_install.backend_guix:

    build_argv  - the only deployment command this adapter can produce, with both
                  paths pinned to the installer-owned constants;

    SchemeString - quoting for an already-validated value.

  The comments in the Python are the design and the port keeps them as behaviour:

  * build_argv refuses any configuration path or mountpoint other than the
    installer-owned ones. It is not a parameter check - it is what stops a caller
    from pointing the deployment at a path it chose;

  * SchemeString is not the security boundary. Validation is; this only keeps a
    value from breaking the generated file's syntax. A port that treated quoting
    as sanitising would be the bug this comment exists to prevent.

  Not compiled here: no FPC in this environment. The vectors were produced by
  running the Python functions. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

const
  GUIX_PROGRAM = 'guix';
  GUIX_CONFIGURATION_PATH = '/run/wsm/system.scm';
  GUIX_TARGET_MOUNTPOINT = '/mnt';

type
  TArgvError = (aeNone, aeConfigPath, aeMountpoint);

function ArgvErrorName(E: TArgvError): string;
function ValidateArgv(const ConfigurationPath, TargetMountpoint: string): TArgvError;
function BuildArgv(const ConfigurationPath, TargetMountpoint: string): string;
function SchemeString(const Value: string): string;

implementation

function ArgvErrorName(E: TArgvError): string;
begin
  case E of
    aeNone: Result := '';
    aeConfigPath: Result := 'argv.config_path';
    aeMountpoint: Result := 'argv.mountpoint';
  end;
end;

function ValidateArgv(const ConfigurationPath, TargetMountpoint: string): TArgvError;
begin
  if ConfigurationPath <> GUIX_CONFIGURATION_PATH then
    Exit(aeConfigPath);
  if TargetMountpoint <> GUIX_TARGET_MOUNTPOINT then
    Exit(aeMountpoint);
  Result := aeNone;
end;

function BuildArgv(const ConfigurationPath, TargetMountpoint: string): string;
begin
  if ValidateArgv(ConfigurationPath, TargetMountpoint) <> aeNone then
    raise Exception.Create('argv: ' + ArgvErrorName(ValidateArgv(ConfigurationPath, TargetMountpoint)));
  Result := GUIX_PROGRAM + ' system init ' + ConfigurationPath + ' ' + TargetMountpoint;
end;

{ Backslash first, then quote: doing it the other way round would double-escape
  the backslash that the quote replacement just introduced. }
function SchemeString(const Value: string): string;
var
  Escaped: string;
begin
  Escaped := StringReplace(Value, '\', '\\', [rfReplaceAll]);
  Escaped := StringReplace(Escaped, '"', '\"', [rfReplaceAll]);
  Result := '"' + Escaped + '"';
end;

end.
