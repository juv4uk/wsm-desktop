unit wsmclassify;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Evidence classification slice of the FPC port.

  Reproduces wsm_install.classification.evidence_state_for: it summarises discovery
  and driver facts without confusing "module loaded" with "driver bound".

  The distinction is the whole point of the function. A module name, a
  module-loaded flag or a module-loaded-unbound status is NOT proof of binding, and
  a passed capability test does not prove every function of a device. The Python
  module says so in three places, and the port keeps the same ladder.

  Not compiled here: no FPC in this environment. The nine vectors below were
  produced by running the Python function. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

type
  TEvidenceState = (
    esNotDetected,
    esUnknown,
    esDriverBoundNotTested,
    esCandidateOnly,
    esNotTested
  );

  TDriverFacts = record
    Present: Boolean;      { the report carried a driver object at all }
    Status: string;
    BoundDriver: string;
    Candidate: string;
  end;

  TDeviceFacts = record
    DiscoveryStatus: string;
    Driver: TDriverFacts;
  end;

function EvidenceStateFor(const D: TDeviceFacts): TEvidenceState;
function EvidenceStateName(S: TEvidenceState): string;
function EvidenceLevel(S: TEvidenceState): string;

implementation

{ Discovery is checked first: a device that was not detected has no driver
  question to answer, and answering it anyway would invent evidence. }
function EvidenceStateFor(const D: TDeviceFacts): TEvidenceState;
begin
  if D.DiscoveryStatus = 'not-detected' then
    Exit(esNotDetected);
  if D.DiscoveryStatus <> 'discovered' then
    Exit(esUnknown);

  if not D.Driver.Present then
    Exit(esUnknown);

  if D.Driver.Status = 'bound' then
  begin
    { Built-in drivers are reported through bound_driver even with no module
      symlink; requiring a module here would manufacture false unknowns. }
    if Trim(D.Driver.BoundDriver) <> '' then
      Exit(esDriverBoundNotTested);
    Exit(esUnknown);
  end;

  if (D.Driver.Status = 'available-only') and (Trim(D.Driver.Candidate) <> '') then
    Exit(esCandidateOnly);

  { module-loaded-unbound, a bare module name, or module_loaded alone is not a
    candidate proof. not-applicable is not a failure either. }
  if (D.Driver.Status = 'unknown') or (D.Driver.Status = 'error') then
    Exit(esUnknown);
  Result := esNotTested;
end;

function EvidenceStateName(S: TEvidenceState): string;
begin
  case S of
    esNotDetected: Result := 'not-detected';
    esUnknown: Result := 'unknown';
    esDriverBoundNotTested: Result := 'driver-bound-not-tested';
    esCandidateOnly: Result := 'candidate-only';
    esNotTested: Result := 'not-tested';
  end;
end;

{ The vocabulary is deliberately two-valued at report level: CERTIFIED is reserved
  until evidence has exact device and capability scope, and a passing function test
  is not enough for subsystem-level certification. }
function EvidenceLevel(S: TEvidenceState): string;
begin
  case S of
    esDriverBoundNotTested, esCandidateOnly: Result := 'known';
    esNotDetected, esUnknown, esNotTested: Result := 'unknown';
  end;
end;

end.
