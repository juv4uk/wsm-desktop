unit wsm_sha256;
{ SHA-256 (FIPS 180-4) for WSM. Written by hand because FPC 3.2.2 -- the
  version packaged by Guix -- ships no SHA-256 unit at all. See
  docs/FPC-FIRST-SLICE-PLAN.md, section "SHA-256".

  Licence: LicenseRef-Volnist (same as the rest of wsm-desktop). }

{$mode objfpc}{$H+}{$modeswitch advancedrecords}
{$WARN 5024 off} { unused parameter }

interface

uses
  SysUtils;

type
  TSHA256Digest = packed array[0..31] of Byte;

  TSHA256 = record
  private
    FState: array[0..7] of LongWord;
    FBuf: array[0..63] of Byte;
    FIndex: LongWord;
    FByteLen: QWord;
    procedure Compress;
  public
    procedure Init;
    procedure Update(P: PByte; Len: PtrUInt); overload;
    procedure Update(const S: RawByteString); overload;
    function Final: TSHA256Digest;
  end;

function SHA256Digest(const S: RawByteString): TSHA256Digest;
function SHA256Hexa(const S: RawByteString): AnsiString;
function DigestHexa(const D: TSHA256Digest): AnsiString;

implementation

const
  K: array[0..63] of LongWord = (
    $428a2f98, $71374491, $b5c0fbcf, $e9b5dba5, $3956c25b, $59f111f1,
    $923f82a4, $ab1c5ed5, $d807aa98, $12835b01, $243185be, $550c7dc3,
    $72be5d74, $80deb1fe, $9bdc06a7, $c19bf174, $e49b69c1, $efbe4786,
    $0fc19dc6, $240ca1cc, $2de92c6f, $4a7484aa, $5cb0a9dc, $76f988da,
    $983e5152, $a831c66d, $b00327c8, $bf597fc7, $c6e00bf3, $d5a79147,
    $06ca6351, $14292967, $27b70a85, $2e1b2138, $4d2c6dfc, $53380d13,
    $650a7354, $766a0abb, $81c2c92e, $92722c85, $a2bfe8a1, $a81a664b,
    $c24b8b70, $c76c51a3, $d192e819, $d6990624, $f40e3585, $106aa070,
    $19a4c116, $1e376c08, $2748774c, $34b0bcb5, $391c0cb3, $4ed8aa4a,
    $5b9cca4f, $682e6ff3, $748f82ee, $78a5636f, $84c87814, $8cc70208,
    $90befffa, $a4506ceb, $bef9a3f7, $c67178f2);

  HEXDIGITS: array[0..15] of AnsiChar = '0123456789abcdef';

function RotR(X: LongWord; N: Byte): LongWord; inline;
begin
  { FPC's RorDWord would do, but an explicit shift pair keeps this unit free
    of any dependency on compiler intrinsics. }
  Result := (X shr N) or (X shl (32 - N));
end;

procedure TSHA256.Init;
begin
  FState[0] := $6a09e667;
  FState[1] := $bb67ae85;
  FState[2] := $3c6ef372;
  FState[3] := $a54ff53a;
  FState[4] := $510e527f;
  FState[5] := $9b05688c;
  FState[6] := $1f83d9ab;
  FState[7] := $5be0cd19;
  FIndex := 0;
  FByteLen := 0;
  FillChar(FBuf, SizeOf(FBuf), 0);
end;

procedure TSHA256.Compress;
var
  W: array[0..63] of LongWord;
  A, B, C, D, E, F, G, H, T1, T2: LongWord;
  I: Integer;
begin
  for I := 0 to 15 do
    W[I] := (LongWord(FBuf[I * 4]) shl 24)
         or (LongWord(FBuf[I * 4 + 1]) shl 16)
         or (LongWord(FBuf[I * 4 + 2]) shl 8)
         or  LongWord(FBuf[I * 4 + 3]);
  for I := 16 to 63 do
    W[I] := (RotR(W[I - 2], 17) xor RotR(W[I - 2], 19) xor (W[I - 2] shr 10))
          + W[I - 7]
          + (RotR(W[I - 15], 7) xor RotR(W[I - 15], 18) xor (W[I - 15] shr 3))
          + W[I - 16];

  A := FState[0]; B := FState[1]; C := FState[2]; D := FState[3];
  E := FState[4]; F := FState[5]; G := FState[6]; H := FState[7];

  for I := 0 to 63 do
  begin
    T1 := H + (RotR(E, 6) xor RotR(E, 11) xor RotR(E, 25))
        + ((E and F) xor ((not E) and G)) + K[I] + W[I];
    T2 := (RotR(A, 2) xor RotR(A, 13) xor RotR(A, 22))
        + ((A and B) xor (A and C) xor (B and C));
    H := G; G := F; F := E; E := D + T1;
    D := C; C := B; B := A; A := T1 + T2;
  end;

  Inc(FState[0], A); Inc(FState[1], B); Inc(FState[2], C); Inc(FState[3], D);
  Inc(FState[4], E); Inc(FState[5], F); Inc(FState[6], G); Inc(FState[7], H);
end;

procedure TSHA256.Update(P: PByte; Len: PtrUInt);
var
  N: PtrUInt;
begin
  Inc(FByteLen, Len);
  while Len > 0 do
  begin
    N := 64 - FIndex;
    if N > Len then
      N := Len;
    Move(P^, FBuf[FIndex], N);
    Inc(FIndex, LongWord(N));
    Inc(P, N);
    Dec(Len, N);
    if FIndex = 64 then
    begin
      Compress;
      FIndex := 0;
    end;
  end;
end;

procedure TSHA256.Update(const S: RawByteString);
begin
  if Length(S) > 0 then
    Update(PByte(PAnsiChar(S)), PtrUInt(Length(S)));
end;

function TSHA256.Final: TSHA256Digest;
var
  Bits: QWord;
  Pad: array[0..71] of Byte;
  PadLen: Integer;
  I: Integer;
begin
  { The bit length is captured *before* the padding is fed through Update,
    because Update keeps incrementing FByteLen. }
  Bits := FByteLen shl 3;

  FillChar(Pad, SizeOf(Pad), 0);
  Pad[0] := $80;
  PadLen := 1;
  while ((FIndex + PadLen) mod 64) <> 56 do
    Inc(PadLen);
  Update(PByte(@Pad[0]), PtrUInt(PadLen));

  for I := 0 to 7 do
    Pad[I] := Byte(Bits shr (56 - 8 * I));
  Update(PByte(@Pad[0]), 8);

  for I := 0 to 7 do
  begin
    Result[I * 4]     := Byte(FState[I] shr 24);
    Result[I * 4 + 1] := Byte(FState[I] shr 16);
    Result[I * 4 + 2] := Byte(FState[I] shr 8);
    Result[I * 4 + 3] := Byte(FState[I]);
  end;
end;

function SHA256Digest(const S: RawByteString): TSHA256Digest;
var
  Ctx: TSHA256;
begin
  Ctx.Init;
  Ctx.Update(S);
  Result := Ctx.Final;
end;

function DigestHexa(const D: TSHA256Digest): AnsiString;
var
  I: Integer;
begin
  SetLength(Result, 64);
  for I := 0 to 31 do
  begin
    Result[I * 2 + 1] := HEXDIGITS[D[I] shr 4];
    Result[I * 2 + 2] := HEXDIGITS[D[I] and 15];
  end;
end;

function SHA256Hexa(const S: RawByteString): AnsiString;
begin
  Result := DigestHexa(SHA256Digest(S));
end;

end.
