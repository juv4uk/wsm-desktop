{ SPDX-License-Identifier: LicenseRef-Volnist }
{
  wsm-profile, FPC edition: decide whether an evidence bundle is acceptable.

  Scope, stated plainly because the boundary is the point: this unit performs
  the SEMANTIC checks only.

    * the schema version must be exactly the supported one - a reader that
      silently upgrades an unknown bundle version would accept evidence it does
      not understand;
    * every declared path must be relative and must not climb out of the bundle
      (absolute paths and `..` are rejected before anything is opened);
    * at least one verified function must have status `pass' - a bundle of only
      not-assessed entries is a hypothesis, not evidence;
    * duplicate artifact paths are rejected: one path, one manifest entry;
    * every declared artifact file must exist.

  NOT performed here: digest verification. Comparing a recorded SHA-256 with
  the bytes on disk needs a hash implementation, and shipping an unverified
  SHA-256 in Pascal would be worse than delegating. The output says so in
  `digest_verification`, so no caller can mistake this for a full check.

  It reads only. It never writes and never executes anything.
}
program wsm_profile;

{$mode objfpc}{$H+}

uses
  SysUtils, Classes, fpjson, jsonparser;

const
  SupportedSchema = 'wsm-profile-evidence/2';

type
  TStringArray = array of string;

var
  Problems: TStringArray;
  ProblemCount: Integer = 0;

procedure AddProblem(const Text: string);
begin
  SetLength(Problems, ProblemCount + 1);
  Problems[ProblemCount] := Text;
  Inc(ProblemCount);
end;

function Str(Obj: TJSONObject; const Key: string): string;
begin
  Result := '';
  if Obj.IndexOfName(Key) >= 0 then
    Result := Obj.Get(Key, '');
end;

{ Absolute paths and `..' segments are rejected before any file is opened:
  a bundle that points outside itself is not a bundle, and following it would
  turn a data file into a filesystem instruction. }
function PathProblem(const RawPath, Label: string): string;
var
  Part: string;
  Rest: string;
begin
  Result := '';
  if RawPath = '' then
  begin
    Result := Label + ': empty path';
    Exit;
  end;
  if (RawPath[1] = '/') or (Copy(RawPath, 1, 3) = '..\') or (Copy(RawPath, 1, 3) = '../') then
  begin
    Result := Label + ': ' + RawPath + ' is not a safe relative path';
    Exit;
  end;
  Rest := RawPath;
  while Rest <> '' do
  begin
    Part := Rest;
    if Pos('/', Rest) > 0 then
    begin
      Part := Copy(Rest, 1, Pos('/', Rest) - 1);
      Rest := Copy(Rest, Pos('/', Rest) + 1, Length(Rest));
    end
    else
      Rest := '';
    if Part = '..' then
    begin
      Result := Label + ': ' + RawPath + ' escapes the bundle directory';
      Exit;
    end;
  end;
end;

function CheckBundle(const Document: TJSONObject; const ArtifactRoot: string): Boolean;
var
  Version: string;
  Source: TJSONObject;
  Artifacts, Functions: TJSONArray;
  I, J: Integer;
  Item: TJSONObject;
  Seen: TStringList;
  DeclaredPath, Issue: string;
  AnyPass: Boolean;
  FullPath: string;
begin
  Version := Str(Document, 'schema');
  if Version <> SupportedSchema then
  begin
    AddProblem('schema-version: ''' + Version + ''' is not ''' + SupportedSchema +
               '''; this reader does not upgrade an unknown bundle version');
    Exit(False);
  end;

  { Path safety first: the actionable reason is a filesystem one, not a shape one. }
  if Document.IndexOfName('profile_source') >= 0 then
    if Document.Find('profile_source') is TJSONObject then
    begin
      Source := TJSONObject(Document.Find('profile_source'));
      Issue := PathProblem(Str(Source, 'path'), 'profile_source');
      if Issue <> '' then
        AddProblem(Issue);
    end;

  Seen := TStringList.Create;
  try
    Seen.Sorted := True;
    Seen.Duplicates := dupIgnore;

    if Document.IndexOfName('artifacts') >= 0 then
      if Document.Find('artifacts') is TJSONArray then
      begin
        Artifacts := TJSONArray(Document.Find('artifacts'));
        for I := 0 to Artifacts.Count - 1 do
        begin
          if not (Artifacts.Items[I] is TJSONObject) then
            Continue;
          Item := TJSONObject(Artifacts.Items[I]);
          DeclaredPath := Str(Item, 'path');
          Issue := PathProblem(DeclaredPath, 'artifacts/' + IntToStr(I));
          if Issue <> '' then
          begin
            AddProblem(Issue);
            Continue;
          end;
          if Seen.IndexOf(DeclaredPath) >= 0 then
            AddProblem('duplicate artifact path ''' + DeclaredPath +
                       '''; each path must have exactly one manifest entry')
          else
            Seen.Add(DeclaredPath);

          FullPath := IncludeTrailingPathDelimiter(ArtifactRoot) + DeclaredPath;
          if not FileExists(FullPath) then
            AddProblem('artifacts/' + IntToStr(I) + ': ' + DeclaredPath +
                       ' does not exist under the bundle directory');
        end;
      end;
  finally
    Seen.Free;
  end;

  AnyPass := False;
  if Document.IndexOfName('verified_functions') >= 0 then
    if Document.Find('verified_functions') is TJSONArray then
    begin
      Functions := TJSONArray(Document.Find('verified_functions'));
      for J := 0 to Functions.Count - 1 do
      begin
        if not (Functions.Items[J] is TJSONObject) then
          Continue;
        Item := TJSONObject(Functions.Items[J]);
        if Str(Item, 'status') = 'pass' then
          AnyPass := True;
      end;
    end;

  if not AnyPass then
    AddProblem('no function passed: a bundle with only not-assessed entries is a ' +
               'hypothesis, not evidence');

  Result := ProblemCount = 0;
end;

var
  Text: TStringList;
  Parser: TJSONParser;
  Root: TJSONObject;
  Ok: Boolean;
  I: Integer;
begin
  if ParamCount <> 1 then
  begin
    WriteLn(StdErr, 'usage: wsm-profile EVIDENCE.json');
    Halt(2);
  end;

  Text := TStringList.Create;
  try
    try
      Text.LoadFromFile(ParamStr(1));
    except
      on E: Exception do
      begin
        WriteLn(StdErr, 'wsm-profile: cannot read ', ParamStr(1), ': ', E.Message);
        Halt(3);
      end;
    end;

    Parser := nil;
    try
      try
        Parser := TJSONParser.Create(Text.Text);
        if not (Parser.Parse is TJSONObject) then
        begin
          WriteLn(StdErr, 'wsm-profile: evidence is not a JSON object');
          Halt(4);
        end;
        Root := TJSONObject(Parser.Parse);
      except
        on E: Exception do
        begin
          WriteLn(StdErr, 'wsm-profile: evidence is not valid JSON: ', E.Message);
          Halt(4);
        end;
      end;

      Ok := CheckBundle(Root, ExtractFileDir(ExpandFileName(ParamStr(1))));

      Write('{"ok":', Ok, ',"schema":"', SupportedSchema, '"');
      Write(',"digest_verification":"delegated"');
      Write(',"problems":[');
      for I := 0 to ProblemCount - 1 do
      begin
        if I > 0 then Write(',');
        Write('"', Problems[I], '"');
      end;
      WriteLn(']}');

      if not Ok then
        Halt(5);
    finally
      Parser.Free;
    end;
  finally
    Text.Free;
  end;
end.
