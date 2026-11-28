unit wsmtui_scripted;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ The screen a test drives: keys in, frames out, no terminal.

  This is the second implementation of IScreen, and the reason the interface is
  narrow. It has no termios, no ANSI, no timing: a key sequence is a list of
  tokens and a frame is a list of strings, which is exactly what the golden
  vectors compare.

  The tokens are the same strings the Python tests use ("up", "down", "enter",
  "esc", "backspace", "quit") plus literal characters, because
  tests/test_tui.py drives the real flow with them. A key list that runs out
  yields "quit", matching the Python FakeScreen. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, wsmtui;

type
  TFrameList = array of TStringArray;

  TScriptedScreen = class(TInterfacedObject, IScreen)
  private
    FKeys: TStringArray;
    FNext: Integer;
    FFrames: TFrameList;
  public
    { Not Create: TInterfacedObject.Create takes no arguments and an override
      would have to match its signature. }
    constructor CreateScripted(const Keys: TStringArray);
    procedure Render(const Lines: TStringArray);
    function ReadKey: string;
    function FrameCount: Integer;
    function Frame(Index: Integer): TStringArray;
    function KeysConsumed: Integer;
  end;

implementation

constructor TScriptedScreen.CreateScripted(const Keys: TStringArray);
begin
  inherited Create;
  FKeys := Keys;
  FNext := 0;
  FFrames := nil;
end;

procedure TScriptedScreen.Render(const Lines: TStringArray);
begin
  SetLength(FFrames, Length(FFrames) + 1);
  FFrames[High(FFrames)] := Lines;
end;

function TScriptedScreen.ReadKey: string;
begin
  if FNext > High(FKeys) then
    Exit('quit');
  Result := FKeys[FNext];
  Inc(FNext);
end;

function TScriptedScreen.FrameCount: Integer;
begin
  Result := Length(FFrames);
end;

function TScriptedScreen.Frame(Index: Integer): TStringArray;
begin
  if (Index < 0) or (Index > High(FFrames)) then
  begin
    Result := nil;
    Exit;
  end;
  Result := FFrames[Index];
end;

function TScriptedScreen.KeysConsumed: Integer;
begin
  Result := FNext;
end;

end.
