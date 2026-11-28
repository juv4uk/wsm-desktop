{ SPDX-License-Identifier: LicenseRef-Volnist }

unit wsmjson;
{$mode objfpc}{$H+}

{ A deliberately small, read-only JSON document model for the WSM installer
  front end.

  Why not fcl-json: this unit is the only thing the installer front end needs
  from a JSON library, and it needs it on a 2 GB live medium where every unit
  in the closure is paid for. It also needs to keep the *lexeme* of a number
  rather than a re-rendered float, so that a value the report author wrote is
  reported back unchanged.

  What it does not do: it never writes anything except a string in memory, it
  has no schema support, no references, and no streaming. Parsing is strict —
  duplicate object keys are accepted with the last one winning (like Python's
  json module) and trailing content after the value is an error (also like
  Python's json module).

  The writer sorts object keys and indents by two spaces, which is what
  `json.dumps(..., indent=2, sort_keys=True)` produces. It exists so that the
  FPC front end can emit a summary a Python reader can diff. }

interface

uses
  SysUtils;

type
  TWsmJsonKind = (jkNull, jkFalse, jkTrue, jkNumber, jkString, jkArray, jkObject);

  { Raised for malformed input. The message names a line and a column; the
    exact wording is not part of any contract, only the fact of the refusal. }
  EWsmJsonError = class(Exception);

  { FPC rejects an anonymous `array of Integer` as a function result type:
  it needs a named type, and the error it gives ("Type identifier expected")
  points at the keyword rather than at the cause. }
  TWsmIntegerArray = array of Integer;

  TWsmJson = class
  private
    FKind: TWsmJsonKind;
    FText: string;
    FItems: array of TWsmJson;
    FNames: array of string;
    FValues: array of TWsmJson;
    function RenderAt(ASpacesPerLevel, ALevel: Integer): string;
    function SortedMemberOrder: TWsmIntegerArray;
  public
    constructor Create(AKind: TWsmJsonKind);
    destructor Destroy; override;

    class function NewNull: TWsmJson;
    class function NewBoolean(AValue: Boolean): TWsmJson;
    class function NewNumber(const ALexeme: string): TWsmJson;
    class function NewString(const AValue: string): TWsmJson;
    class function NewArray: TWsmJson;
    class function NewObject: TWsmJson;

    procedure AddItem(AValue: TWsmJson);
    procedure AddMember(const AName: string; AValue: TWsmJson);

    function Kind: TWsmJsonKind;
    function KindName: string;
    function IsNull: Boolean;
    function IsBoolean: Boolean;
    function IsTrue: Boolean;
    function IsNumber: Boolean;
    function IsString: Boolean;
    function IsArray: Boolean;
    function IsObject: Boolean;
    function IsIntegerNumber: Boolean;

    { Array item count, or object member count. }
    function Count: Integer;
    function Item(AIndex: Integer): TWsmJson;
    function MemberName(AIndex: Integer): string;
    { Returns nil when this is not an object or the member is absent. }
    function Member(const AName: string): TWsmJson;
    function HasMember(const AName: string): Boolean;

    function AsText: string;
    function AsLexeme: string;
    function AsInteger: Int64;

    { A deep copy. The caller owns the result. }
    function Clone: TWsmJson;

    { Deterministic rendering: object keys sorted, two-space indent by default. }
    function Render(ASpacesPerLevel: Integer = 2): string;
    { The value as Python's repr() would spell it, for messages that quote a
      rejected value. Arrays and objects are not reproduced faithfully. }
    function PythonRepr: string;
  end;

{ Parse a complete JSON document. Raises EWsmJsonError. }
function ParseJson(const ASource: string): TWsmJson;
{ JSON string escaping compatible with Python's json.dumps(ensure_ascii=False). }
function WsmJsonEscape(const AText: string): string;
{ UTF-8 encoding of one code point, used by the \uXXXX escape. }
function WsmCodePointToUtf8(ACode: LongWord): string;

implementation

function WsmCodePointToUtf8(ACode: LongWord): string;
begin
  if ACode < $80 then
    Result := Chr(ACode)
  else if ACode < $800 then
    Result := Chr($C0 or (ACode shr 6)) + Chr($80 or (ACode and $3F))
  else if ACode < $10000 then
    Result := Chr($E0 or (ACode shr 12)) + Chr($80 or ((ACode shr 6) and $3F)) +
              Chr($80 or (ACode and $3F))
  else
    Result := Chr($F0 or ((ACode shr 18) and $07)) +
              Chr($80 or ((ACode shr 12) and $3F)) +
              Chr($80 or ((ACode shr 6) and $3F)) +
              Chr($80 or (ACode and $3F));
end;

function WsmJsonEscape(const AText: string): string;
var
  Index: Integer;
  Current: Char;
begin
  Result := '';
  for Index := 1 to Length(AText) do
  begin
    Current := AText[Index];
    case Current of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #8: Result := Result + '\b';
      #9: Result := Result + '\t';
      #10: Result := Result + '\n';
      #12: Result := Result + '\f';
      #13: Result := Result + '\r';
      #0..#7, #11, #14..#31:
        Result := Result + '\u' + IntToHex(Ord(Current), 4);
    else
      Result := Result + Current;
    end;
  end;
end;

constructor TWsmJson.Create(AKind: TWsmJsonKind);
begin
  inherited Create;
  FKind := AKind;
  FText := '';
end;

destructor TWsmJson.Destroy;
var
  Index: Integer;
begin
  for Index := 0 to High(FItems) do
    FItems[Index].Free;
  for Index := 0 to High(FValues) do
    FValues[Index].Free;
  FItems := nil;
  FValues := nil;
  inherited Destroy;
end;

class function TWsmJson.NewNull: TWsmJson;
begin
  Result := TWsmJson.Create(jkNull);
end;

class function TWsmJson.NewBoolean(AValue: Boolean): TWsmJson;
begin
  if AValue then
    Result := TWsmJson.Create(jkTrue)
  else
    Result := TWsmJson.Create(jkFalse);
end;

class function TWsmJson.NewNumber(const ALexeme: string): TWsmJson;
begin
  Result := TWsmJson.Create(jkNumber);
  Result.FText := ALexeme;
end;

class function TWsmJson.NewString(const AValue: string): TWsmJson;
begin
  Result := TWsmJson.Create(jkString);
  Result.FText := AValue;
end;

class function TWsmJson.NewArray: TWsmJson;
begin
  Result := TWsmJson.Create(jkArray);
end;

class function TWsmJson.NewObject: TWsmJson;
begin
  Result := TWsmJson.Create(jkObject);
end;

procedure TWsmJson.AddItem(AValue: TWsmJson);
begin
  SetLength(FItems, Length(FItems) + 1);
  FItems[High(FItems)] := AValue;
end;

procedure TWsmJson.AddMember(const AName: string; AValue: TWsmJson);
var
  Index: Integer;
begin
  { Python's json.loads keeps the last duplicate key. }
  for Index := 0 to High(FNames) do
    if FNames[Index] = AName then
    begin
      FValues[Index].Free;
      FValues[Index] := AValue;
      Exit;
    end;
  SetLength(FNames, Length(FNames) + 1);
  SetLength(FValues, Length(FValues) + 1);
  FNames[High(FNames)] := AName;
  FValues[High(FValues)] := AValue;
end;

function TWsmJson.Kind: TWsmJsonKind;
begin
  Result := FKind;
end;

function TWsmJson.KindName: string;
begin
  case FKind of
    jkNull: Result := 'null';
    jkFalse: Result := 'false';
    jkTrue: Result := 'true';
    jkNumber: Result := 'number';
    jkString: Result := 'string';
    jkArray: Result := 'array';
    jkObject: Result := 'object';
  else
    Result := 'unknown';
  end;
end;

function TWsmJson.IsNull: Boolean;
begin
  Result := FKind = jkNull;
end;

function TWsmJson.IsBoolean: Boolean;
begin
  Result := (FKind = jkTrue) or (FKind = jkFalse);
end;

function TWsmJson.IsTrue: Boolean;
begin
  Result := FKind = jkTrue;
end;

function TWsmJson.IsNumber: Boolean;
begin
  Result := FKind = jkNumber;
end;

function TWsmJson.IsString: Boolean;
begin
  Result := FKind = jkString;
end;

function TWsmJson.IsArray: Boolean;
begin
  Result := FKind = jkArray;
end;

function TWsmJson.IsObject: Boolean;
begin
  Result := FKind = jkObject;
end;

function TWsmJson.IsIntegerNumber: Boolean;
var
  Index: Integer;
begin
  Result := FKind = jkNumber;
  if not Result then
    Exit;
  for Index := 1 to Length(FText) do
    if FText[Index] in ['.', 'e', 'E'] then
      Exit(False);
end;

function TWsmJson.Count: Integer;
begin
  if FKind = jkArray then
    Result := Length(FItems)
  else if FKind = jkObject then
    Result := Length(FNames)
  else
    Result := 0;
end;

function TWsmJson.Item(AIndex: Integer): TWsmJson;
begin
  if (FKind = jkArray) and (AIndex >= 0) and (AIndex < Length(FItems)) then
    Result := FItems[AIndex]
  else
    Result := nil;
end;

function TWsmJson.MemberName(AIndex: Integer): string;
begin
  if (FKind = jkObject) and (AIndex >= 0) and (AIndex < Length(FNames)) then
    Result := FNames[AIndex]
  else
    Result := '';
end;

function TWsmJson.Member(const AName: string): TWsmJson;
var
  Index: Integer;
begin
  Result := nil;
  if FKind <> jkObject then
    Exit;
  for Index := 0 to High(FNames) do
    if FNames[Index] = AName then
      Exit(FValues[Index]);
end;

function TWsmJson.HasMember(const AName: string): Boolean;
begin
  Result := Member(AName) <> nil;
end;

function TWsmJson.AsText: string;
begin
  if FKind = jkString then
    Result := FText
  else
    Result := '';
end;

function TWsmJson.AsLexeme: string;
begin
  if FKind = jkNumber then
    Result := FText
  else
    Result := '';
end;

function TWsmJson.AsInteger: Int64;
begin
  if FKind = jkNumber then
    Result := StrToInt64Def(FText, 0)
  else
    Result := 0;
end;

function TWsmJson.PythonRepr: string;
begin
  case FKind of
    jkNull: Result := 'None';
    jkTrue: Result := 'True';
    jkFalse: Result := 'False';
    jkString: Result := '''' + FText + '''';
    jkNumber: Result := FText;
    jkArray: Result := '<list>';
    jkObject: Result := '<dict>';
  else
    Result := '<unknown>';
  end;
end;

function TWsmJson.SortedMemberOrder: TWsmIntegerArray;
var
  Index, Scan, Holds: Integer;
begin
  SetLength(Result, Length(FNames));
  for Index := 0 to High(FNames) do
    Result[Index] := Index;
  { Insertion sort: report objects are small and this keeps the unit free of
    the generics and comparer machinery the rest of the program does not use. }
  for Index := 1 to High(Result) do
  begin
    Holds := Result[Index];
    Scan := Index - 1;
    while (Scan >= 0) and (FNames[Result[Scan]] > FNames[Holds]) do
    begin
      Result[Scan + 1] := Result[Scan];
      Dec(Scan);
    end;
    Result[Scan + 1] := Holds;
  end;
end;

function TWsmJson.RenderAt(ASpacesPerLevel, ALevel: Integer): string;
var
  Index: Integer;
  Order: TWsmIntegerArray;
  Pad, Inner: string;
  First: Boolean;
begin
  Pad := StringOfChar(' ', ASpacesPerLevel * ALevel);
  Inner := StringOfChar(' ', ASpacesPerLevel * (ALevel + 1));
  case FKind of
    jkNull: Result := 'null';
    jkTrue: Result := 'true';
    jkFalse: Result := 'false';
    jkNumber: Result := FText;
    jkString: Result := '"' + WsmJsonEscape(FText) + '"';
    jkArray:
      begin
        if Length(FItems) = 0 then
          Exit('[]');
        Result := '[' + LineEnding;
        for Index := 0 to High(FItems) do
        begin
          Result := Result + Inner + FItems[Index].RenderAt(ASpacesPerLevel, ALevel + 1);
          if Index < High(FItems) then
            Result := Result + ',';
          Result := Result + LineEnding;
        end;
        Result := Result + Pad + ']';
      end;
    jkObject:
      begin
        if Length(FNames) = 0 then
          Exit('{}');
        Order := SortedMemberOrder;
        Result := '{' + LineEnding;
        First := True;
        for Index := 0 to High(Order) do
        begin
          if not First then
            Result := Result + ',' + LineEnding;
          First := False;
          Result := Result + Inner + '"' + WsmJsonEscape(FNames[Order[Index]]) + '": ' +
                    FValues[Order[Index]].RenderAt(ASpacesPerLevel, ALevel + 1);
        end;
        Result := Result + LineEnding + Pad + '}';
      end;
  else
    Result := 'null';
  end;
end;

function TWsmJson.Clone: TWsmJson;
var
  Index: Integer;
begin
  Result := TWsmJson.Create(FKind);
  Result.FText := FText;
  for Index := 0 to High(FItems) do
    Result.AddItem(FItems[Index].Clone);
  for Index := 0 to High(FNames) do
    Result.AddMember(FNames[Index], FValues[Index].Clone);
end;

function TWsmJson.Render(ASpacesPerLevel: Integer): string;
begin
  Result := RenderAt(ASpacesPerLevel, 0);
end;

type
  TJsonReader = class
  private
    FSource: string;
    FPosition: Integer;
    procedure SkipWhitespace;
    function Peek: Char;
    function AtEnd: Boolean;
    procedure Fail(const AMessage: string);
    function Where: string;
    function ReadValue: TWsmJson;
    function ReadObject: TWsmJson;
    function ReadArray: TWsmJson;
    function ReadString: string;
    function ReadNumber: string;
    function ReadHex4: LongWord;
  public
    constructor Create(const ASource: string);
    function ReadDocument: TWsmJson;
  end;

constructor TJsonReader.Create(const ASource: string);
begin
  inherited Create;
  FSource := ASource;
  FPosition := 1;
end;

function TJsonReader.AtEnd: Boolean;
begin
  Result := FPosition > Length(FSource);
end;

function TJsonReader.Peek: Char;
begin
  if AtEnd then
    Result := #0
  else
    Result := FSource[FPosition];
end;

function TJsonReader.Where: string;
var
  Index, Line, Column: Integer;
begin
  Line := 1;
  Column := 1;
  for Index := 1 to FPosition - 1 do
  begin
    if FSource[Index] = #10 then
    begin
      Inc(Line);
      Column := 1;
    end
    else
      Inc(Column);
  end;
  Result := Format('line %d column %d', [Line, Column]);
end;

procedure TJsonReader.Fail(const AMessage: string);
begin
  raise EWsmJsonError.CreateFmt('%s: %s', [AMessage, Where]);
end;

procedure TJsonReader.SkipWhitespace;
begin
  while (not AtEnd) and (FSource[FPosition] in [' ', #9, #10, #13]) do
    Inc(FPosition);
end;

function TJsonReader.ReadHex4: LongWord;
var
  Index: Integer;
  Digit: Integer;
  Current: Char;
begin
  Result := 0;
  for Index := 1 to 4 do
  begin
    if AtEnd then
      Fail('unterminated \u escape');
    Current := FSource[FPosition];
    if (Current >= '0') and (Current <= '9') then
      Digit := Ord(Current) - Ord('0')
    else if (Current >= 'a') and (Current <= 'f') then
      Digit := Ord(Current) - Ord('a') + 10
    else if (Current >= 'A') and (Current <= 'F') then
      Digit := Ord(Current) - Ord('A') + 10
    else
      Fail('invalid \u escape');
    Result := (Result shl 4) or LongWord(Digit);
    Inc(FPosition);
  end;
end;

function TJsonReader.ReadString: string;
var
  Current: Char;
  Code, LowPart: LongWord;
begin
  Result := '';
  if Peek <> '"' then
    Fail('expected a string');
  Inc(FPosition);
  while True do
  begin
    if AtEnd then
      Fail('unterminated string');
    Current := FSource[FPosition];
    Inc(FPosition);
    if Current = '"' then
      Exit;
    if Current = '\' then
    begin
      if AtEnd then
        Fail('unterminated escape');
      Current := FSource[FPosition];
      Inc(FPosition);
      case Current of
        '"': Result := Result + '"';
        '\': Result := Result + '\';
        '/': Result := Result + '/';
        'b': Result := Result + #8;
        'f': Result := Result + #12;
        'n': Result := Result + #10;
        'r': Result := Result + #13;
        't': Result := Result + #9;
        'u':
          begin
            Code := ReadHex4;
            { Surrogate pair: combine, otherwise the code point stands alone. }
            if (Code >= $D800) and (Code <= $DBFF) and (not AtEnd) and
               (FSource[FPosition] = '\') and (FPosition < Length(FSource)) and
               (FSource[FPosition + 1] = 'u') then
            begin
              Inc(FPosition, 2);
              LowPart := ReadHex4;
              if (LowPart >= $DC00) and (LowPart <= $DFFF) then
                Code := $10000 + ((Code - $D800) shl 10) + (LowPart - $DC00)
              else
                Code := $FFFD;
            end;
            Result := Result + WsmCodePointToUtf8(Code);
          end;
      else
        Fail('invalid escape');
      end;
      Continue;
    end;
    if Ord(Current) < 32 then
      Fail('control character in string');
    Result := Result + Current;
  end;
end;

function TJsonReader.ReadNumber: string;
var
  Start: Integer;
begin
  Start := FPosition;
  if Peek = '-' then
    Inc(FPosition);
  if AtEnd or (not (Peek in ['0'..'9'])) then
    Fail('invalid number');
  if Peek = '0' then
    Inc(FPosition)
  else
    while (not AtEnd) and (Peek in ['0'..'9']) do
      Inc(FPosition);
  if (not AtEnd) and (Peek = '.') then
  begin
    Inc(FPosition);
    if AtEnd or (not (Peek in ['0'..'9'])) then
      Fail('invalid number');
    while (not AtEnd) and (Peek in ['0'..'9']) do
      Inc(FPosition);
  end;
  if (not AtEnd) and (Peek in ['e', 'E']) then
  begin
    Inc(FPosition);
    if (not AtEnd) and (Peek in ['+', '-']) then
      Inc(FPosition);
    if AtEnd or (not (Peek in ['0'..'9'])) then
      Fail('invalid number');
    while (not AtEnd) and (Peek in ['0'..'9']) do
      Inc(FPosition);
  end;
  Result := Copy(FSource, Start, FPosition - Start);
end;

function TJsonReader.ReadArray: TWsmJson;
begin
  Result := TWsmJson.NewArray;
  try
    Inc(FPosition); // '['
    SkipWhitespace;
    if Peek = ']' then
    begin
      Inc(FPosition);
      Exit;
    end;
    while True do
    begin
      SkipWhitespace;
      Result.AddItem(ReadValue);
      SkipWhitespace;
      if Peek = ',' then
      begin
        Inc(FPosition);
        Continue;
      end;
      if Peek = ']' then
      begin
        Inc(FPosition);
        Exit;
      end;
      Fail('expected , or ]');
    end;
  except
    Result.Free;
    raise;
  end;
end;

function TJsonReader.ReadObject: TWsmJson;
var
  Name: string;
begin
  Result := TWsmJson.NewObject;
  try
    Inc(FPosition); // '{'
    SkipWhitespace;
    if Peek = '}' then
    begin
      Inc(FPosition);
      Exit;
    end;
    while True do
    begin
      SkipWhitespace;
      Name := ReadString;
      SkipWhitespace;
      if Peek <> ':' then
        Fail('expected :');
      Inc(FPosition);
      SkipWhitespace;
      Result.AddMember(Name, ReadValue);
      SkipWhitespace;
      if Peek = ',' then
      begin
        Inc(FPosition);
        Continue;
      end;
      if Peek = '}' then
      begin
        Inc(FPosition);
        Exit;
      end;
      Fail('expected , or }');
    end;
  except
    Result.Free;
    raise;
  end;
end;

function TJsonReader.ReadValue: TWsmJson;
begin
  SkipWhitespace;
  if AtEnd then
    Fail('unexpected end of document');
  case Peek of
    '{': Result := ReadObject;
    '[': Result := ReadArray;
    '"': Result := TWsmJson.NewString(ReadString);
    't':
      begin
        if Copy(FSource, FPosition, 4) <> 'true' then
          Fail('invalid literal');
        Inc(FPosition, 4);
        Result := TWsmJson.NewBoolean(True);
      end;
    'f':
      begin
        if Copy(FSource, FPosition, 5) <> 'false' then
          Fail('invalid literal');
        Inc(FPosition, 5);
        Result := TWsmJson.NewBoolean(False);
      end;
    'n':
      begin
        if Copy(FSource, FPosition, 4) <> 'null' then
          Fail('invalid literal');
        Inc(FPosition, 4);
        Result := TWsmJson.NewNull;
      end;
    '-', '0'..'9': Result := TWsmJson.NewNumber(ReadNumber);
  else
    Fail('unexpected character');
  end;
end;

function TJsonReader.ReadDocument: TWsmJson;
begin
  SkipWhitespace;
  if AtEnd then
    Fail('expecting value');
  Result := ReadValue;
  try
    SkipWhitespace;
    if not AtEnd then
      Fail('extra data after the document');
  except
    Result.Free;
    raise;
  end;
end;

function ParseJson(const ASource: string): TWsmJson;
var
  Reader: TJsonReader;
begin
  Reader := TJsonReader.Create(ASource);
  try
    Result := Reader.ReadDocument;
  finally
    Reader.Free;
  end;
end;

end.
