unit wsmpaths;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Safe relative path slice of the FPC port.

  Reproduces wsm_install.profile._safe_relative_path_problem: the rule that decides
  whether a path inside a profile-evidence bundle may be opened at all.

  This is the only place in the port that looks at strings a report supplied, so it
  is the one that has to refuse rather than repair. Absolute paths, traversal,
  backslashes, drive letters, doubled separators and non-canonical forms are all
  refused - not normalised, because normalising "a/../b" to "b" would accept a
  document that said something else.

  Not compiled here: no FPC in this environment. The ten vectors below were
  produced by running the Python function. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

{ Returns an empty string when the path is safe, otherwise the refusal text in the
  same shape Python produces. }
function SafeRelativePathProblem(const RawPath, Label: string): string;

implementation

function HasEmptyOrDotPart(const Path: string): Boolean;
var
  Part: string;
  Start, I: Integer;
begin
  Start := 1;
  for I := 1 to Length(Path) + 1 do
    if (I = Length(Path) + 1) or (Path[I] = '/') then
    begin
      Part := Copy(Path, Start, I - Start);
      if (Part = '') or (Part = '.') or (Part = '..') then
        Exit(True);
      Start := I + 1;
    end;
  Result := False;
end;

function SafeRelativePathProblem(const RawPath, Label: string): string;
begin
  { The order of these conditions mirrors Python so the refusal is identical for a
    path that breaks more than one rule at once. }
  if (RawPath = '')
     or (Pos('\', RawPath) > 0)
     or (Pos(':', RawPath) > 0)
     or (RawPath[1] = '/')
     or HasEmptyOrDotPart(RawPath) then
    Exit(Label + '/path is not a safe relative path: ' + QuotedStr(RawPath));
  Result := '';
end;

end.
