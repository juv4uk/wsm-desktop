unit wsmfresh;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Report freshness slice of the FPC port.

  Reproduces the two digests from wsm_install.freshness:

    derive_boot_session_digest - a domain-separated hash of the boot ID, so the raw
    boot ID is never returned or persisted;

    topology_digest - a hash over non-sensitive hardware topology facts only,
    excluding local paths and serials, so a report can be compared across sessions
    without carrying anything that identifies the machine.

  Both are SHA-256 over bytes; wsm_sha256 supplies the primitive because FPC 3.2.2
  has none.

  Not compiled here: no FPC in this environment. The self-check compares against
  vectors produced by running the Python code, so a divergence shows up on the
  first run. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, wsm_sha256;

const
  { The domain prefix is part of the contract: changing it changes every digest.
    The trailing NUL is deliberate and is what Python hashes. }
  BOOT_DOMAIN = 'wsm-desktop/boot-session/v1';

function DeriveBootSessionDigest(const BootId: string): string;

{ Topology facts, in the order Python filters them. Anything not in this list -
  serial, local path - never reaches the hash. }
function TopologyDigest(const Normalized: string): string;

implementation

function DeriveBootSessionDigest(const BootId: string): string;
var
  Trimmed, Payload: RawByteString;
begin
  Trimmed := RawByteString(Trim(BootId));
  if Trimmed = '' then
    raise Exception.Create('boot_id must be a non-empty string');
  { Domain, then a NUL byte, then the trimmed id - exactly what Python concatenates. }
  Payload := RawByteString(BOOT_DOMAIN) + #0 + Trimmed;
  Result := string(SHA256Hexa(Payload));
end;

{ Takes the already-normalized topology document as canonical JSON. Building that
  document from device records belongs to the caller: this unit owns the hash, not
  the selection, and splitting it that way keeps the exclusion rule in one place
  that a test can read. }
function TopologyDigest(const Normalized: string): string;
begin
  Result := string(SHA256Hexa(RawByteString(Normalized)));
end;

end.
