unit wsmverdict;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Verdict aggregation slice of the FPC port.

  Reproduces wsm_install.preflight_env.verdict: three-valued aggregation over
  preflight criteria, where a check that did not run makes the whole result
  incomplete rather than pass.

  The rule is the reason the module exists. The installer has many ways to fail for
  reasons unrelated to the target disk - a missing mkfs.fat, no guix, a /mnt
  already in use - and each is cheap to detect and expensive to discover at step
  five of seven, after the disk has been wiped.

  "incomplete is not a pass: a check that did not run proves nothing" is the note
  the Python returns with every verdict, and it is kept verbatim here because it is
  the contract, not a comment.

  Not compiled here: no FPC in this environment. The five vectors below were
  produced by running the Python function. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

type
  TCriterionStatus = (csPass, csFail, csNotRun);
  TVerdict = (vPass, vFail, vIncomplete);

function CriterionStatusName(S: TCriterionStatus): string;
function VerdictName(V: TVerdict): string;
function VerdictOf(const Statuses: array of TCriterionStatus): TVerdict;
function VerdictNote: string;

implementation

function CriterionStatusName(S: TCriterionStatus): string;
begin
  case S of
    csPass: Result := 'pass';
    csFail: Result := 'fail';
    csNotRun: Result := 'not-run';
  end;
end;

function VerdictName(V: TVerdict): string;
begin
  case V of
    vPass: Result := 'pass';
    vFail: Result := 'fail';
    vIncomplete: Result := 'incomplete';
  end;
end;

{ fail wins over not-run, and not-run wins over pass. The order matters: a single
  failed check is a decision, while a missing one is only an absence of evidence,
  and reporting an absence as a failure would hide which one it was. }
function VerdictOf(const Statuses: array of TCriterionStatus): TVerdict;
var
  I: Integer;
  SawNotRun: Boolean;
begin
  SawNotRun := False;
  for I := 0 to High(Statuses) do
  begin
    if Statuses[I] = csFail then
      Exit(vFail);
    if Statuses[I] = csNotRun then
      SawNotRun := True;
  end;
  if SawNotRun then
    Result := vIncomplete
  else
    Result := vPass;
end;

function VerdictNote: string;
begin
  Result := 'incomplete is not a pass: a check that did not run proves nothing';
end;

end.
