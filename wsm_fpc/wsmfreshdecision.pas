unit wsmfreshdecision;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Freshness decision slice of the FPC port.

  Reproduces wsm_install.freshness.evaluate_freshness: it fails closed unless report
  bytes, boot session, age, environment and topology all match.

  The order of the checks is the design. A malformed digest is not a mismatch - it
  is unverifiable, because nothing was compared. A mismatch between the report and
  the plan is not the same as a mismatch between the report and the live session,
  and both are reported as session-mismatch but for different reasons. Reporting a
  missing value as a mismatch would claim a comparison that never happened.

  age_seconds is deliberately absent from most refusals: it is only known once the
  clock check passed, and returning a number computed from a clock that already
  contradicted itself would invite someone to trust it.

  Not compiled here: no FPC in this environment. The nine vectors below were
  produced by running the Python function. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

type
  TFreshnessStatus = (
    fsFresh, fsStale, fsSessionMismatch, fsReportDigestMismatch,
    fsEnvironmentMismatch, fsTopologyChanged, fsUnverifiable
  );

  TReportFreshness = record
    ReportSha256: string;
    BootSessionSha256: string;
    CollectedMonotonicNs: Int64;
    Architecture: string;
    KernelRelease: string;
    BootMode: string;
    TopologySha256: string;
  end;

  TLiveSession = record
    BootSessionSha256: string;
    MonotonicNowNs: Int64;
    Architecture: string;
    KernelRelease: string;
    BootMode: string;
    TopologySha256: string;
  end;

  TFreshnessDecision = record
    Status: TFreshnessStatus;
    Reason: string;
    HasAge: Boolean;
    AgeSeconds: Double;
  end;

function FreshnessStatusName(S: TFreshnessStatus): string;
function IsDigest(const Value: string): Boolean;
function EvaluateFreshness(const Report: TReportFreshness; const Live: TLiveSession;
                           const ExpectedReportSha256, ExpectedBootSessionSha256: string;
                           MaxAgeSeconds: Integer): TFreshnessDecision;

implementation

function FreshnessStatusName(S: TFreshnessStatus): string;
begin
  case S of
    fsFresh: Result := 'fresh';
    fsStale: Result := 'stale';
    fsSessionMismatch: Result := 'session-mismatch';
    fsReportDigestMismatch: Result := 'report-digest-mismatch';
    fsEnvironmentMismatch: Result := 'environment-mismatch';
    fsTopologyChanged: Result := 'topology-changed';
    fsUnverifiable: Result := 'unverifiable';
  end;
end;

{ Lowercase hex, exactly 64 characters. Anything else is not a digest and cannot
  be compared. }
function IsDigest(const Value: string): Boolean;
var
  I: Integer;
  C: Char;
begin
  if Length(Value) <> 64 then
    Exit(False);
  for I := 1 to 64 do
  begin
    C := Value[I];
    if not (((C >= '0') and (C <= '9')) or ((C >= 'a') and (C <= 'f'))) then
      Exit(False);
  end;
  Result := True;
end;

function Decision(S: TFreshnessStatus; const Reason: string): TFreshnessDecision;
begin
  Result.Status := S;
  Result.Reason := Reason;
  Result.HasAge := False;
  Result.AgeSeconds := 0;
end;

function DecisionWithAge(S: TFreshnessStatus; const Reason: string;
                         Age: Double): TFreshnessDecision;
begin
  Result.Status := S;
  Result.Reason := Reason;
  Result.HasAge := True;
  Result.AgeSeconds := Age;
end;

function EvaluateFreshness(const Report: TReportFreshness; const Live: TLiveSession;
                           const ExpectedReportSha256, ExpectedBootSessionSha256: string;
                           MaxAgeSeconds: Integer): TFreshnessDecision;
var
  Age: Double;
  ReportEnv, LiveEnv: string;
begin
  if MaxAgeSeconds < 1 then
    raise Exception.Create('max_age_seconds must be a positive integer');

  if (not IsDigest(Report.ReportSha256)) or (not IsDigest(ExpectedReportSha256)) then
    Exit(Decision(fsUnverifiable, 'report digest is missing or malformed'));
  if Report.ReportSha256 <> ExpectedReportSha256 then
    Exit(Decision(fsReportDigestMismatch,
                  'report bytes differ from the report bound into the draft plan'));

  if not IsDigest(ExpectedBootSessionSha256) then
    Exit(Decision(fsUnverifiable, 'plan-bound boot-session identity is unavailable'));
  if (not IsDigest(Report.BootSessionSha256)) or (not IsDigest(Live.BootSessionSha256)) then
    Exit(Decision(fsUnverifiable, 'boot-session identity is unavailable'));
  if Report.BootSessionSha256 <> ExpectedBootSessionSha256 then
    Exit(Decision(fsSessionMismatch,
                  'source report boot session differs from the session bound into the draft plan'));
  if Report.BootSessionSha256 <> Live.BootSessionSha256 then
    Exit(Decision(fsSessionMismatch, 'report was collected during a different boot session'));

  if (Report.CollectedMonotonicNs < 0) or (Live.MonotonicNowNs < 0)
     or (Live.MonotonicNowNs < Report.CollectedMonotonicNs) then
    Exit(Decision(fsUnverifiable,
                  'same-boot monotonic collection time is unavailable or inconsistent'));

  Age := (Live.MonotonicNowNs - Report.CollectedMonotonicNs) / 1000000000.0;
  if Age > MaxAgeSeconds then
    Exit(DecisionWithAge(fsStale,
                         Format('report age %.3fs exceeds %ds', [Age, MaxAgeSeconds]), Age));

  ReportEnv := Report.Architecture + '|' + Report.KernelRelease + '|' + Report.BootMode;
  LiveEnv := Live.Architecture + '|' + Live.KernelRelease + '|' + Live.BootMode;
  if (Report.Architecture = '') or (Report.KernelRelease = '') or (Report.BootMode = '')
     or (Live.Architecture = '') or (Live.KernelRelease = '') or (Live.BootMode = '') then
    Exit(DecisionWithAge(fsUnverifiable,
                         'architecture, kernel release or boot mode is unavailable', Age));
  if ReportEnv <> LiveEnv then
    Exit(DecisionWithAge(fsEnvironmentMismatch,
                         'live architecture, kernel release or boot mode changed', Age));

  if (not IsDigest(Report.TopologySha256)) or (not IsDigest(Live.TopologySha256)) then
    Exit(DecisionWithAge(fsUnverifiable, 'hardware topology digest is unavailable', Age));
  if Report.TopologySha256 <> Live.TopologySha256 then
    Exit(DecisionWithAge(fsTopologyChanged,
                         'revalidated device topology differs from the source report', Age));

  Result := DecisionWithAge(fsFresh,
    'report bytes, boot session, age, environment and topology match', Age);
end;

end.
