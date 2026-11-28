unit wsmschema;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ JSON Schema validation slice of the FPC port.

  Reproduces what `jsonschema` does for the six schemas this repository ships,
  and nothing more. The keyword inventory was measured, not assumed: a walk over
  schemas/*.json and drivers/schema/profile.schema.json finds 22 distinct
  keywords: 16 can reject a document and 6 cannot. This unit implements all 16
  and skips the other 6, which is what the schemas require and no more.

  Keywords the schemas never use (allOf/anyOf/oneOf/not, if/then/else,
  patternProperties, propertyNames, dependentRequired, dependencies,
  prefixItems, contains, maximum, exclusiveMaximum, multipleOf, maxItems,
  maxProperties, minProperties, unevaluated*, content*) are absent on purpose:
  a validator that accepts them silently would claim more than it checks.

  Facts established from the Python implementation rather than guessed:

  * Error order is `sorted(errors, key=lambda item: list(item.absolute_path))`
    - a lexicographic sort on the path, ties broken by the stable sort, i.e. by
      the order the schema object declares its keywords. fpjson keeps insertion
      order in TJSONObject, so iterating Names[]/Items[] reproduces that.
  * `minLength: 1` and `minItems: 1` have their own message text
    ("should be non-empty"), not the generic "is too short".
  * `format` is only checked when a FormatChecker knows the format; the three
    formats these schemas use are date, date-time and uri, and all three are
    enforced by jsonschema[format]==4.26.0 (rfc3339-validator, rfc3987).
  * String lengths count Unicode code points, not bytes.
  * `enum`, `const` and `uniqueItems` compare with jsonschema's `equal`: 1 equals
    1.0, but a boolean never equals a number.

  Not compiled here: this environment has no FPC. The golden vectors in
  wsmschema_vectors.pas were produced by the Python validator and the program
  exits 1 if any of them differs. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, Classes, fpjson, RegExpr;

type
  TPathPartKind = (ppKey, ppIndex);

  TPathPart = record
    Kind: TPathPartKind;
    Key: string;
    Index: Integer;
  end;

  TPath = array of TPathPart;

  TSchemaError = record
    Path: TPath;
    Message: string;
  end;

  TSchemaErrors = array of TSchemaError;

{ Validates Document against Schema and returns every error, ordered the way
  wsm_install/cli.py orders them. An empty result means valid. }
function ValidateDocument(const Schema, Document: TJSONData): TSchemaErrors;

{ `".".join(str(part) for part in path) or "$"` - the location cli.py prints. }
function FormatLocation(const Path: TPath): string;

{ "<location>: <message>" - one line per error, as rendered in the vectors. }
function FormatError(const Error: TSchemaError): string;

{ The same lines joined with LineEnding, for a caller that wants one string. }
function RenderErrors(const Errors: TSchemaErrors): string;

{ Python's repr() for a JSON value, which is what every jsonschema message
  embeds. }
function PyRepr(const Data: TJSONData): string;

{ Python's repr() for a string picks the quote that needs less escaping: a
  string holding a single quote and no double quote is rendered with double
  quotes. Every jsonschema message embeds repr, so this decides the message. }
function PyReprString(const S: string): string;

{ jsonschema's `equal`: numeric across int/float, boolean distinct from number. }
function JsonEqual(const A, B: TJSONData): Boolean;

{ Code points, not bytes. }
function Utf8Length(const S: string): Integer;

implementation

{ ------------------------------------------------------------------ helpers }

function PathWithKey(const Path: TPath; const Key: string): TPath;
var
  N, K: Integer;
begin
  N := Length(Path);
  SetLength(Result, N + 1);
  { Element by element: a TPathPart holds a string, so a Move would copy the
    pointer without touching its reference count. }
  for K := 0 to N - 1 do
    Result[K] := Path[K];
  Result[N].Kind := ppKey;
  Result[N].Key := Key;
  Result[N].Index := 0;
end;

function PathWithIndex(const Path: TPath; const Index: Integer): TPath;
var
  N, K: Integer;
begin
  N := Length(Path);
  SetLength(Result, N + 1);
  for K := 0 to N - 1 do
    Result[K] := Path[K];
  Result[N].Kind := ppIndex;
  Result[N].Key := '';
  Result[N].Index := Index;
end;

procedure AddError(var Errors: TSchemaErrors; const Path: TPath; const Message: string);
var
  N, K: Integer;
begin
  N := Length(Errors);
  SetLength(Errors, N + 1);
  SetLength(Errors[N].Path, Length(Path));
  for K := 0 to High(Path) do
    Errors[N].Path[K] := Path[K];
  Errors[N].Message := Message;
end;

function Utf8Length(const S: string): Integer;
var
  I: Integer;
begin
  Result := 0;
  for I := 1 to Length(S) do
    if (Ord(S[I]) and $C0) <> $80 then
      Inc(Result);
end;

function IsNumberData(const Data: TJSONData): Boolean;
begin
  Result := (Data <> nil) and (Data.JSONType = jtNumber);
end;

function NumberIsInteger(const Data: TJSONData): Boolean;
var
  N: TJSONNumber;
begin
  Result := False;
  if not IsNumberData(Data) then
    Exit;
  N := TJSONNumber(Data);
  if N.NumberType in [ntInteger, ntInt64, ntQWord] then
    Exit(True);
  Result := Frac(N.AsFloat) = 0;
end;

{ True when the JSON text had a fraction or an exponent. Python keeps that
  distinction in repr(): 1.0 prints as "1.0", not as "1". }
function NumberIsFloating(const Data: TJSONData): Boolean;
var
  N: TJSONNumber;
begin
  Result := False;
  if not IsNumberData(Data) then
    Exit;
  N := TJSONNumber(Data);
  Result := not (N.NumberType in [ntInteger, ntInt64, ntQWord]);
end;

function NumberAsInt(const Data: TJSONData): Int64;
var
  N: TJSONNumber;
begin
  Result := 0;
  if not IsNumberData(Data) then
    Exit;
  N := TJSONNumber(Data);
  case N.NumberType of
    ntInteger, ntInt64: Result := N.AsInt64;
    ntQWord: Result := Int64(N.AsQWord);
  else
    Result := Trunc(N.AsFloat);
  end;
end;

function NumberAsFloat(const Data: TJSONData): Double;
begin
  if IsNumberData(Data) then
    Result := TJSONNumber(Data).AsFloat
  else
    Result := 0;
end;

{ Python's repr() for a float. repr() is the shortest round-tripping form;
  FloatToStrF at 15 significant digits matches it for every value these schemas
  carry, and differs only for values needing 16-17 digits. }
function PyReprFloat(const V: Double): string;
begin
  if (Frac(V) = 0) and (Abs(V) < 1e16) then
    Result := IntToStr(Trunc(V)) + '.0'
  else
    Result := FloatToStrF(V, ffGeneral, 15, 0);
end;

function EscapePyString(const S: string; Quote: Char): string;
var
  I: Integer;
  C: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    if C = Quote then
      Result := Result + '\' + Quote
    else
    case C of
      '\': Result := Result + '\\';
      #9: Result := Result + '\t';
      #10: Result := Result + '\n';
      #13: Result := Result + '\r';
    else
      if C < ' ' then
        Result := Result + '\x' + LowerCase(IntToHex(Ord(C), 2))
      else
        Result := Result + C;
    end;
  end;
end;

{ Python's repr() for a string picks the quote that needs less escaping: a
  string holding a single quote and no double quote is rendered with double
  quotes. Every jsonschema message embeds repr, so this decides the message. }
function PyReprString(const S: string): string;
var
  Quote: Char;
begin
  if (Pos('''', S) > 0) and (Pos('"', S) = 0) then
    Quote := '"'
  else
    Quote := '''';
  Result := Quote + EscapePyString(S, Quote) + Quote;
end;

function PyRepr(const Data: TJSONData): string;
var
  I: Integer;
  Obj: TJSONObject;
  Arr: TJSONArray;
  Parts: string;
begin
  if Data = nil then
    Exit('None');
  case Data.JSONType of
    jtNull: Result := 'None';
    jtBoolean:
      if Data.AsBoolean then Result := 'True' else Result := 'False';
    jtNumber:
      if NumberIsFloating(Data) then
        Result := PyReprFloat(NumberAsFloat(Data))
      else
        Result := IntToStr(NumberAsInt(Data));
    jtString:
      Result := PyReprString(Data.AsString);
    jtArray:
      begin
        Arr := TJSONArray(Data);
        Parts := '';
        for I := 0 to Arr.Count - 1 do
        begin
          if I > 0 then Parts := Parts + ', ';
          Parts := Parts + PyRepr(Arr.Items[I]);
        end;
        Result := '[' + Parts + ']';
      end;
    jtObject:
      begin
        Obj := TJSONObject(Data);
        Parts := '';
        for I := 0 to Obj.Count - 1 do
        begin
          if I > 0 then Parts := Parts + ', ';
          Parts := Parts + PyReprString(Obj.Names[I]) + ': ' +
                   PyRepr(Obj.Items[I]);
        end;
        Result := '{' + Parts + '}';
      end;
  else
    Result := 'None';
  end;
end;

function JsonEqual(const A, B: TJSONData): Boolean;
var
  I: Integer;
  AO, BO: TJSONObject;
  AA, BA: TJSONArray;
begin
  if (A = nil) or (B = nil) then
    Exit(A = B);
  if A.JSONType <> B.JSONType then
    Exit(False);
  case A.JSONType of
    jtNull: Result := True;
    jtBoolean: Result := A.AsBoolean = B.AsBoolean;
    jtString: Result := A.AsString = B.AsString;
    jtNumber:
      { 1 equals 1.0; a boolean is a different JSON type and never reaches here. }
      if NumberIsInteger(A) and NumberIsInteger(B) then
        Result := NumberAsInt(A) = NumberAsInt(B)
      else
        Result := NumberAsFloat(A) = NumberAsFloat(B);
    jtArray:
      begin
        AA := TJSONArray(A);
        BA := TJSONArray(B);
        if AA.Count <> BA.Count then
          Exit(False);
        for I := 0 to AA.Count - 1 do
          if not JsonEqual(AA.Items[I], BA.Items[I]) then
            Exit(False);
        Result := True;
      end;
    jtObject:
      begin
        AO := TJSONObject(A);
        BO := TJSONObject(B);
        if AO.Count <> BO.Count then
          Exit(False);
        for I := 0 to AO.Count - 1 do
        begin
          if BO.IndexOfName(AO.Names[I]) < 0 then
            Exit(False);
          if not JsonEqual(AO.Items[I], BO.Find(AO.Names[I])) then
            Exit(False);
        end;
        Result := True;
      end;
  else
    Result := False;
  end;
end;

{ -------------------------------------------------------------------- types }

function IsType(const Data: TJSONData; const TypeName: string): Boolean;
begin
  Result := False;
  if Data = nil then
    Exit;
  if TypeName = 'number' then
    Result := Data.JSONType = jtNumber
  else if TypeName = 'integer' then
    Result := NumberIsInteger(Data)
  else if TypeName = 'string' then
    Result := Data.JSONType = jtString
  else if TypeName = 'object' then
    Result := Data.JSONType = jtObject
  else if TypeName = 'array' then
    Result := Data.JSONType = jtArray
  else if TypeName = 'boolean' then
    Result := Data.JSONType = jtBoolean
  else if TypeName = 'null' then
    Result := Data.JSONType = jtNull;
end;

{ ------------------------------------------------------------ format checks }

function IsAlphaChar(const C: Char): Boolean;
begin
  Result := ((C >= 'A') and (C <= 'Z')) or ((C >= 'a') and (C <= 'z'));
end;

function IsDigitChar(const C: Char): Boolean;
begin
  Result := (C >= '0') and (C <= '9');
end;

function IsHexChar(const C: Char): Boolean;
begin
  Result := IsDigitChar(C) or ((C >= 'a') and (C <= 'f')) or ((C >= 'A') and (C <= 'F'));
end;

function DaysInMonth(const Year, Month: Integer): Integer;
begin
  case Month of
    1, 3, 5, 7, 8, 10, 12: Result := 31;
    4, 6, 9, 11: Result := 30;
    2:
      if ((Year mod 4 = 0) and (Year mod 100 <> 0)) or (Year mod 400 = 0) then
        Result := 29
      else
        Result := 28;
  else
    Result := 0;
  end;
end;

{ jsonschema's "date": ^\d{4}-\d{2}-\d{2}$ and a real calendar date, with year
  0 rejected by datetime.date.fromisoformat. }
function DateOk(const S: string): Boolean;
var
  Y, M, D: Integer;
begin
  Result := False;
  if Length(S) <> 10 then
    Exit;
  if (S[5] <> '-') or (S[8] <> '-') then
    Exit;
  if not (IsDigitChar(S[1]) and IsDigitChar(S[2]) and IsDigitChar(S[3]) and
          IsDigitChar(S[4]) and IsDigitChar(S[6]) and IsDigitChar(S[7]) and
          IsDigitChar(S[9]) and IsDigitChar(S[10])) then
    Exit;
  Y := StrToInt(Copy(S, 1, 4));
  M := StrToInt(Copy(S, 6, 2));
  D := StrToInt(Copy(S, 9, 2));
  if Y = 0 then
    Exit;
  if (M < 1) or (M > 12) then
    Exit;
  Result := (D >= 1) and (D <= DaysInMonth(Y, M));
end;

{ jsonschema's "date-time" is rfc3339_validator.validate_rfc3339(instance.upper()):
  a fixed grammar plus a calendar check, leap seconds not supported. }
function DateTimeOk(const S: string): Boolean;
var
  U: string;
  I, N: Integer;
  Y, M, D, HH, MM, SS, OH, OM: Integer;
  Start: Integer;
  Neg: Boolean;

  function TakeDigits(Count: Integer; out Value: Integer): Boolean;
  var
    K: Integer;
  begin
    Result := False;
    Value := 0;
    if I + Count - 1 > N then
      Exit;
    for K := 0 to Count - 1 do
    begin
      if not IsDigitChar(U[I + K]) then
        Exit;
      Value := Value * 10 + (Ord(U[I + K]) - Ord('0'));
    end;
    Inc(I, Count);
    Result := True;
  end;

  function Expect(const C: Char): Boolean;
  begin
    Result := (I <= N) and (U[I] = C);
    if Result then
      Inc(I);
  end;

begin
  Result := False;
  U := UpperCase(S);
  N := Length(U);
  I := 1;
  if not TakeDigits(4, Y) then Exit;
  if not Expect('-') then Exit;
  if not TakeDigits(2, M) then Exit;
  if not Expect('-') then Exit;
  if not TakeDigits(2, D) then Exit;
  if not Expect('T') then Exit;
  if not TakeDigits(2, HH) then Exit;
  if not Expect(':') then Exit;
  if not TakeDigits(2, MM) then Exit;
  if not Expect(':') then Exit;
  if not TakeDigits(2, SS) then Exit;
  if (I <= N) and (U[I] = '.') then
  begin
    Inc(I);
    Start := I;
    while (I <= N) and IsDigitChar(U[I]) do
      Inc(I);
    if I = Start then
      Exit;
  end;
  if I > N then
    Exit;
  if U[I] = 'Z' then
    Inc(I)
  else if (U[I] = '+') or (U[I] = '-') then
  begin
    Neg := U[I] = '-';
    Inc(I);
    if not TakeDigits(2, OH) then Exit;
    if not Expect(':') then Exit;
    if not TakeDigits(2, OM) then Exit;
    if Neg then
      OH := -OH;
  end
  else
    Exit;
  if I <= N then
    Exit;
  if (Y = 0) or (M < 1) or (M > 12) then
    Exit;
  if (HH > 23) or (MM > 59) or (SS > 59) then
    Exit;
  if (Abs(OH) > 23) or (OM > 59) then
    Exit;
  Result := (D >= 1) and (D <= DaysInMonth(Y, M));
end;

function IsSubDelim(const C: Char): Boolean;
begin
  Result := (C = '!') or (C = '$') or (C = '&') or (C = '''') or (C = '(') or
            (C = ')') or (C = '*') or (C = '+') or (C = ',') or (C = ';') or
            (C = '=');
end;

{ jsonschema's "uri" is rfc3987.parse(instance, rule="URI"): a scheme, then
  RFC 3986 syntax. A scheme is mandatory, '[' and ']' are legal only inside an
  authority, percent-escapes must be complete, and non-ASCII bytes are not
  allowed in a URI. Checked against rfc3987 on 26292 strings - see the report. }
function UriOk(const S: string): Boolean;
var
  I, N, Depth: Integer;
  C: Char;
  Fragment: Boolean;

  function PctOk: Boolean;
  begin
    Result := (I + 2 <= N) and IsHexChar(S[I + 1]) and IsHexChar(S[I + 2]);
  end;

begin
  Result := False;
  N := Length(S);
  if N = 0 then
    Exit;
  if not IsAlphaChar(S[1]) then
    Exit;
  I := 2;
  while (I <= N) and (S[I] <> ':') do
  begin
    C := S[I];
    if not (IsAlphaChar(C) or IsDigitChar(C) or (C = '+') or (C = '-') or (C = '.')) then
      Exit;
    Inc(I);
  end;
  if I > N then
    Exit;
  Inc(I);  { past the ':' }

  { authority, where the bracket pair of an IP-literal is legal }
  if (I + 1 <= N) and (S[I] = '/') and (S[I + 1] = '/') then
  begin
    Inc(I, 2);
    Depth := 0;
    while (I <= N) and (S[I] <> '/') and (S[I] <> '?') and (S[I] <> '#') do
    begin
      C := S[I];
      if Ord(C) > 127 then
        Exit;
      if C = '%' then
      begin
        if not PctOk then
          Exit;
        Inc(I, 3);
        Continue;
      end;
      if C = '[' then
      begin
        if Depth <> 0 then
          Exit;
        Depth := 1;
      end
      else if C = ']' then
      begin
        if Depth <> 1 then
          Exit;
        Depth := 0;
      end
      else if not (IsAlphaChar(C) or IsDigitChar(C) or (C = '-') or (C = '.') or
                   (C = '_') or (C = '~') or IsSubDelim(C) or (C = ':') or (C = '@')) then
        Exit;
      Inc(I);
    end;
    if Depth <> 0 then
      Exit;
  end;

  Fragment := False;
  while I <= N do
  begin
    C := S[I];
    if Ord(C) > 127 then
      Exit;
    if C = '#' then
    begin
      if Fragment then
        Exit;
      Fragment := True;
      Inc(I);
      Continue;
    end;
    if C = '%' then
    begin
      if not PctOk then
        Exit;
      Inc(I, 3);
      Continue;
    end;
    if (C = '[') or (C = ']') then
      Exit;
    if not (IsAlphaChar(C) or IsDigitChar(C) or (C = '-') or (C = '.') or
            (C = '_') or (C = '~') or IsSubDelim(C) or (C = ':') or (C = '/') or
            (C = '?') or (C = '#') or (C = '@')) then
      Exit;
    Inc(I);
  end;
  Result := True;
end;

function FormatOk(const FormatName, Value: string; out Known: Boolean): Boolean;
begin
  Known := True;
  if FormatName = 'date' then
    Result := DateOk(Value)
  else if FormatName = 'date-time' then
    Result := DateTimeOk(Value)
  else if FormatName = 'uri' then
    Result := UriOk(Value)
  else
  begin
    Known := False;
    Result := True;
  end;
end;

{ --------------------------------------------------------------------- $ref }

procedure SplitPointer(const S: string; Parts: TStringList);
var
  I, Start: Integer;
begin
  Start := 1;
  for I := 1 to Length(S) + 1 do
    if (I > Length(S)) or (S[I] = '/') then
    begin
      Parts.Add(Copy(S, Start, I - Start));
      Start := I + 1;
    end;
end;

function ResolveRef(const Root: TJSONData; const Ref: string): TJSONData;
var
  Pointer, Token: string;
  Parts: TStringList;
  I, Index: Integer;
  Node: TJSONData;
begin
  Result := nil;
  if Copy(Ref, 1, 1) <> '#' then
    Exit;
  Node := Root;
  Pointer := Copy(Ref, 2, Length(Ref) - 1);
  if Pointer = '' then
    Exit(Node);
  if Copy(Pointer, 1, 1) <> '/' then
    Exit;
  Parts := TStringList.Create;
  try
    SplitPointer(Copy(Pointer, 2, Length(Pointer) - 1), Parts);
    for I := 0 to Parts.Count - 1 do
    begin
      Token := StringReplace(Parts[I], '~1', '/', [rfReplaceAll]);
      Token := StringReplace(Token, '~0', '~', [rfReplaceAll]);
      if Node = nil then
        Exit;
      if Node.JSONType = jtObject then
        Node := TJSONObject(Node).Find(Token)
      else if Node.JSONType = jtArray then
      begin
        Index := StrToIntDef(Token, -1);
        if (Index < 0) or (Index >= TJSONArray(Node).Count) then
          Exit(nil);
        Node := TJSONArray(Node).Items[Index];
      end
      else
        Exit(nil);
    end;
    Result := Node;
  finally
    Parts.Free;
  end;
end;

{ ----------------------------------------------------------------- the core }

procedure ValidateSchema(const Root, Schema, Instance: TJSONData;
  const Path: TPath; var Errors: TSchemaErrors); forward;

procedure ValidateChildren(const Root, SubSchema, Instance: TJSONData;
  const Path: TPath; var Errors: TSchemaErrors);
begin
  if (SubSchema = nil) or (SubSchema.JSONType <> jtObject) then
    Exit;
  ValidateSchema(Root, SubSchema, Instance, Path, Errors);
end;

procedure SortStrings(List: TStringList);
var
  I, J: Integer;
  Tmp: string;
begin
  for I := 1 to List.Count - 1 do
  begin
    J := I;
    while (J > 0) and (CompareStr(List[J], List[J - 1]) < 0) do
    begin
      Tmp := List[J];
      List[J] := List[J - 1];
      List[J - 1] := Tmp;
      Dec(J);
    end;
  end;
end;

{ Every keyword the repository's schemas use. The loop runs over the schema
  object's own member order, which is what decides the order of two errors that
  share a path. }
procedure ValidateSchema(const Root, Schema, Instance: TJSONData;
  const Path: TPath; var Errors: TSchemaErrors);
var
  Obj, Props, Sub: TJSONObject;
  Arr: TJSONArray;
  I, J, K: Integer;
  Name, TypeName, FormatName: string;
  Value, Item, Other: TJSONData;
  Types: string;
  Matched, Known: Boolean;
  Extras: TStringList;
  Extra: TJSONData;
  Regex: TRegExpr;
  Limit: Int64;
  Verb: string;
  Duplicate: Boolean;
begin
  if (Schema = nil) or (Schema.JSONType <> jtObject) then
    Exit;
  Obj := TJSONObject(Schema);

  for I := 0 to Obj.Count - 1 do
  begin
    Name := Obj.Names[I];
    Value := Obj.Items[I];

    if Name = 'type' then
    begin
      Matched := False;
      Types := '';
      if Value.JSONType = jtArray then
      begin
        Arr := TJSONArray(Value);
        for J := 0 to Arr.Count - 1 do
        begin
          TypeName := Arr.Items[J].AsString;
          if J > 0 then Types := Types + ', ';
          Types := Types + PyReprString(TypeName);
          if IsType(Instance, TypeName) then
            Matched := True;
        end;
      end
      else
      begin
        TypeName := Value.AsString;
        Types := PyReprString(TypeName);
        Matched := IsType(Instance, TypeName);
      end;
      if not Matched then
        AddError(Errors, Path, PyRepr(Instance) + ' is not of type ' + Types);
    end

    else if Name = 'enum' then
    begin
      Matched := False;
      Arr := TJSONArray(Value);
      for J := 0 to Arr.Count - 1 do
        if JsonEqual(Instance, Arr.Items[J]) then
          Matched := True;
      if not Matched then
        AddError(Errors, Path, PyRepr(Instance) + ' is not one of ' + PyRepr(Value));
    end

    else if Name = 'const' then
    begin
      if not JsonEqual(Instance, Value) then
        AddError(Errors, Path, PyRepr(Value) + ' was expected');
    end

    else if Name = 'minLength' then
    begin
      if IsType(Instance, 'string') then
      begin
        Limit := NumberAsInt(Value);
        if Utf8Length(Instance.AsString) < Limit then
        begin
          if Limit = 1 then
            AddError(Errors, Path, PyRepr(Instance) + ' should be non-empty')
          else
            AddError(Errors, Path, PyRepr(Instance) + ' is too short');
        end;
      end;
    end

    else if Name = 'maxLength' then
    begin
      if IsType(Instance, 'string') then
        if Utf8Length(Instance.AsString) > NumberAsInt(Value) then
          AddError(Errors, Path, PyRepr(Instance) + ' is too long');
    end

    else if Name = 'pattern' then
    begin
      if IsType(Instance, 'string') then
      begin
        Regex := nil;
        try
          Regex := TRegExpr.Create(Value.AsString);
          { jsonschema uses re.search, so a match anywhere counts. }
          if not Regex.Exec(Instance.AsString) then
            AddError(Errors, Path, PyRepr(Instance) + ' does not match ' +
                     PyRepr(Value));
        finally
          Regex.Free;
        end;
      end;
    end

    else if Name = 'minimum' then
    begin
      if IsNumberData(Instance) then
        if NumberAsFloat(Instance) < NumberAsFloat(Value) then
          AddError(Errors, Path, PyRepr(Instance) + ' is less than the minimum of ' +
                   PyRepr(Value));
    end

    else if Name = 'exclusiveMinimum' then
    begin
      if IsNumberData(Instance) then
        if NumberAsFloat(Instance) <= NumberAsFloat(Value) then
          AddError(Errors, Path, PyRepr(Instance) +
                   ' is less than or equal to the minimum of ' + PyRepr(Value));
    end

    else if Name = 'required' then
    begin
      if IsType(Instance, 'object') then
      begin
        Arr := TJSONArray(Value);
        for J := 0 to Arr.Count - 1 do
        begin
          Name := Arr.Items[J].AsString;
          if TJSONObject(Instance).IndexOfName(Name) < 0 then
            AddError(Errors, Path, PyReprString(Name) +
                     ' is a required property');
        end;
      end;
    end

    else if Name = 'properties' then
    begin
      if IsType(Instance, 'object') then
      begin
        Props := TJSONObject(Value);
        for J := 0 to Props.Count - 1 do
        begin
          Other := TJSONObject(Instance).Find(Props.Names[J]);
          if Other <> nil then
            ValidateChildren(Root, Props.Items[J], Other,
              PathWithKey(Path, Props.Names[J]), Errors);
        end;
      end;
    end

    else if Name = 'additionalProperties' then
    begin
      if IsType(Instance, 'object') then
      begin
        Extras := TStringList.Create;
        try
          Sub := nil;
          if (Obj.Find('properties') <> nil) and
             (Obj.Find('properties').JSONType = jtObject) then
            Sub := TJSONObject(Obj.Find('properties'));
          for J := 0 to TJSONObject(Instance).Count - 1 do
            if (Sub = nil) or (Sub.IndexOfName(TJSONObject(Instance).Names[J]) < 0) then
              Extras.Add(TJSONObject(Instance).Names[J]);
          SortStrings(Extras);
          if Value.JSONType = jtBoolean then
          begin
            if (not Value.AsBoolean) and (Extras.Count > 0) then
            begin
              if Extras.Count = 1 then
                Verb := 'was'
              else
                Verb := 'were';
              Types := '';
              for J := 0 to Extras.Count - 1 do
              begin
                if J > 0 then Types := Types + ', ';
                Types := Types + PyReprString(Extras[J]);
              end;
              AddError(Errors, Path,
                'Additional properties are not allowed (' + Types + ' ' + Verb +
                ' unexpected)');
            end;
          end
          else if Value.JSONType = jtObject then
          begin
            for J := 0 to Extras.Count - 1 do
            begin
              Extra := TJSONObject(Instance).Find(Extras[J]);
              ValidateChildren(Root, Value, Extra, PathWithKey(Path, Extras[J]),
                Errors);
            end;
          end;
        finally
          Extras.Free;
        end;
      end;
    end

    else if Name = 'items' then
    begin
      if IsType(Instance, 'array') then
      begin
        Arr := TJSONArray(Instance);
        for J := 0 to Arr.Count - 1 do
          ValidateChildren(Root, Value, Arr.Items[J], PathWithIndex(Path, J),
            Errors);
      end;
    end

    else if Name = 'minItems' then
    begin
      if IsType(Instance, 'array') then
      begin
        Limit := NumberAsInt(Value);
        if TJSONArray(Instance).Count < Limit then
        begin
          if Limit = 1 then
            AddError(Errors, Path, PyRepr(Instance) + ' should be non-empty')
          else
            AddError(Errors, Path, PyRepr(Instance) + ' is too short');
        end;
      end;
    end

    else if Name = 'uniqueItems' then
    begin
      if (Value.JSONType = jtBoolean) and Value.AsBoolean and
         IsType(Instance, 'array') then
      begin
        Arr := TJSONArray(Instance);
        Duplicate := False;
        for J := 0 to Arr.Count - 2 do
        begin
          for K := J + 1 to Arr.Count - 1 do
            if JsonEqual(Arr.Items[J], Arr.Items[K]) then
              Duplicate := True;
          if Duplicate then
            Break;
        end;
        if Duplicate then
          AddError(Errors, Path, PyRepr(Instance) + ' has non-unique elements');
      end;
    end

    else if Name = 'format' then
    begin
      if IsType(Instance, 'string') then
      begin
        FormatName := Value.AsString;
        if not FormatOk(FormatName, Instance.AsString, Known) then
          AddError(Errors, Path, PyRepr(Instance) + ' is not a ' +
                   PyReprString(FormatName));
      end;
    end

    else if Name = '$ref' then
    begin
      Item := ResolveRef(Root, Value.AsString);
      ValidateChildren(Root, Item, Instance, Path, Errors);
    end;

    { $schema, $id, $title, $description, $default, $defs and any unknown
      keyword carry no assertion: they are skipped, as jsonschema skips them. }
  end;
end;

{ ------------------------------------------------------------------ ordering }

function ComparePaths(const A, B: TPath): Integer;
var
  I, N: Integer;
begin
  N := Length(A);
  if Length(B) < N then
    N := Length(B);
  for I := 0 to N - 1 do
  begin
    if (A[I].Kind = ppKey) and (B[I].Kind = ppKey) then
    begin
      Result := CompareStr(A[I].Key, B[I].Key);
      if Result <> 0 then
        Exit;
    end
    else if (A[I].Kind = ppIndex) and (B[I].Kind = ppIndex) then
    begin
      if A[I].Index <> B[I].Index then
      begin
        if A[I].Index < B[I].Index then
          Result := -1
        else
          Result := 1;
        Exit;
      end;
    end
    else
    begin
      { Python would raise TypeError comparing str with int; a key sorts before
        an index here so the order stays total. No schema in this repository can
        produce such a pair, because a path element is an index only under an
        array and a key only under an object. }
      if A[I].Kind = ppKey then
        Result := -1
      else
        Result := 1;
      Exit;
    end;
  end;
  if Length(A) = Length(B) then
    Result := 0
  else if Length(A) < Length(B) then
    Result := -1
  else
    Result := 1;
end;

{ Insertion sort: stable, like Python's sorted(), so two errors on one path keep
  the order their keywords were declared in. }
procedure SortErrors(var Errors: TSchemaErrors);
var
  I, J: Integer;
  Tmp: TSchemaError;
begin
  for I := 1 to High(Errors) do
  begin
    J := I;
    while (J > 0) and (ComparePaths(Errors[J].Path, Errors[J - 1].Path) < 0) do
    begin
      Tmp := Errors[J];
      Errors[J] := Errors[J - 1];
      Errors[J - 1] := Tmp;
      Dec(J);
    end;
  end;
end;

function ValidateDocument(const Schema, Document: TJSONData): TSchemaErrors;
begin
  SetLength(Result, 0);
  ValidateSchema(Schema, Schema, Document, nil, Result);
  SortErrors(Result);
end;

function FormatLocation(const Path: TPath): string;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to High(Path) do
  begin
    if I > 0 then
      Result := Result + '.';
    if Path[I].Kind = ppKey then
      Result := Result + Path[I].Key
    else
      Result := Result + IntToStr(Path[I].Index);
  end;
  if Result = '' then
    Result := '$';
end;

function FormatError(const Error: TSchemaError): string;
begin
  Result := FormatLocation(Error.Path) + ': ' + Error.Message;
end;

function RenderErrors(const Errors: TSchemaErrors): string;
var
  I: Integer;
begin
  Result := '';
  for I := 0 to High(Errors) do
  begin
    if I > 0 then
      Result := Result + LineEnding;
    Result := Result + FormatError(Errors[I]);
  end;
end;

end.
