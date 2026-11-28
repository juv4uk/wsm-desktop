program wsmplandigest;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Canonical plan digest - first slice of the FPC port.

  Reproduces wsm_install/plan_digest.py: SHA-256 over JSON with sorted keys, no
  spaces, UTF-8.

  Two facts forced the shape of this file, both established from the toolchain
  rather than guessed:

  * FPC 3.2.2, the version Guix packages, ships NO sha256 unit - the hash package
    has only md5/sha1/crc/ntlm/uuid/hmac/unixcrypt, and the sha256 unit landed in
    trunk after that release. Hence the hand-written wsm_sha256 unit.
  * fpjson cannot produce this document: TJSONObject has no Sort and iterates in
    insertion order, and its escape routine writes control characters with
    UPPERCASE hex (\u001F) where Python writes \u001f. Either difference is a
    different digest. Hence the hand-written serializer below.

  Not compiled here: this environment has no FPC. The three vectors are the
  acceptance test - the program checks itself and exits 1 if any digest differs. }

{$mode objfpc}{$H+}

uses
  SysUtils, wsm_sha256;

const
  SCHEMA = 'wsm-install-plan/1';

type
  TPlanStep = record
    Argv: array of string;
    Destructive: Boolean;
    Purpose: string;
  end;

{ Python's json.dumps escapes exactly these, and lower-case hex for the rest of
  the control range. The Cyrillic case is why this matters: those bytes must pass
  through raw, not as \uXXXX. }
function JsonEscape(const S: string): string;
var
  I: Integer;
  C: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    case C of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #8:  Result := Result + '\b';
      #9:  Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
    else
      if C < ' ' then
        Result := Result + '\u' + LowerCase(IntToHex(Ord(C), 4))
      else
        Result := Result + C;
    end;
  end;
end;

function StepJson(const Step: TPlanStep): string;
var
  I: Integer;
  Argv: string;
begin
  Argv := '';
  for I := 0 to High(Step.Argv) do
  begin
    if I > 0 then Argv := Argv + ',';
    Argv := Argv + '"' + JsonEscape(Step.Argv[I]) + '"';
  end;
  Result := '{"argv":[' + Argv + '],"destructive":' +
            BoolToStr(Step.Destructive, 'true', 'false') +
            ',"purpose":"' + JsonEscape(Step.Purpose) + '"}';
end;

{ Keys sort as disk, schema, steps - the order Python emits. }
function CanonicalPlan(const Disk: string; const Steps: array of TPlanStep): string;
var
  I: Integer;
  Body: string;
begin
  Body := '';
  for I := 0 to High(Steps) do
  begin
    if I > 0 then Body := Body + ',';
    Body := Body + StepJson(Steps[I]);
  end;
  Result := '{"disk":"' + JsonEscape(Disk) + '","schema":"' + SCHEMA +
            '","steps":[' + Body + ']}';
end;

function PlanDigest(const Canonical: string): string;
begin
  Result := string(SHA256Hexa(RawByteString(Canonical)));
end;

function Check(const Name, Canonical, Expected: string): Boolean;
var
  Actual: string;
begin
  Actual := PlanDigest(Canonical);
  Result := Actual = Expected;
  WriteLn(Name);
  WriteLn('  canonical: ', Canonical);
  WriteLn('  expected:  ', Expected);
  WriteLn('  actual:    ', Actual);
  if not Result then WriteLn('  MISMATCH');
end;

var
  Failures: Integer;
  Steps: array[0..0] of TPlanStep;
begin
  Failures := 0;

  { Vector 1: one non-destructive step. }
  SetLength(Steps[0].Argv, 2);
  Steps[0].Argv[0] := 'mkfs.ext4';
  Steps[0].Argv[1] := '/dev/sda1';
  Steps[0].Destructive := False;
  Steps[0].Purpose := 'format';
  if not Check('one non-destructive step', CanonicalPlan('/dev/sda', Steps),
    '6506509e8b85ed5edefc4457ac49c74681dfb64fda595f1f09c8a24450ef7d1a') then
    Inc(Failures);

  { Vector 2: one destructive step. }
  SetLength(Steps[0].Argv, 3);
  Steps[0].Argv[0] := 'wipefs';
  Steps[0].Argv[1] := '-a';
  Steps[0].Argv[2] := '/dev/nvme0n1';
  Steps[0].Destructive := True;
  Steps[0].Purpose := 'clear signatures';
  if not Check('one destructive step', CanonicalPlan('/dev/nvme0n1', Steps),
    'eb541c6c28b7ba4d9f6c3557c71e01dec72ba87dbec969b6a7c3c6436b1915a9') then
    Inc(Failures);

  { Vector 3: Cyrillic purpose - proves the UTF-8 path, which is where a naive
    ByteString port silently produces a different digest. }
  SetLength(Steps[0].Argv, 3);
  Steps[0].Argv[0] := 'sgdisk';
  Steps[0].Argv[1] := '--zap-all';
  Steps[0].Argv[2] := '/dev/sdb';
  Steps[0].Destructive := True;
  Steps[0].Purpose := 'очистити таблицю';
  if not Check('cyrillic purpose', CanonicalPlan('/dev/sdb', Steps),
    '81899745a8324d6733e41e2aecde5147379cfc9524a702be71b58b653cc66492') then
    Inc(Failures);

  WriteLn;
  if Failures = 0 then
  begin
    WriteLn('PASS: all vectors match the Python implementation');
    Halt(0);
  end;
  WriteLn('FAIL: ', Failures, ' vector(s) differ');
  Halt(1);
end.
