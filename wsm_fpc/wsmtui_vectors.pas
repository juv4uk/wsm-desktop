program wsmtui_vectors;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Self-check for the wsmtui unit.

  Every frame below was printed by the repository's Python - the real
  wsm_install/tui.py driven by a scripted key sequence - and copied here
  verbatim; nothing is hand-computed or imagined. Regenerate with the
  commands recorded in FPC-TUI-SLICE.md.

  Three kinds of check, in the order the port needs them:

    1. key -> event, for every key the flow accepts in every state;
    2. layout primitives - the UTF-8 padding, the truncation, the sizes;
    3. whole sessions: scripted keys in, frames out, exit code compared.

  The four sessions below are the required vectors: the initial frame, a
  navigation step, the destructive-step confirmation and a refusal. The
  same harness carries the other eight captured sessions (done, preview
  error, backspace, no disks, firmware, Ukrainian quit, evidence note,
  long path) in the repository; they are the same procedure with a
  different key list and expected frames.

  Not compiled in the environment this was written in: there is no FPC
  there. Run `make check` on a machine with FPC 3.2.2. }

{$mode objfpc}{$H+}

uses
  SysUtils, wsmtui, wsmtui_scripted;

var
  Checks: Integer = 0;
  Failures: Integer = 0;
  PreviewCalls: Integer = 0;
  PreviewPath: string = '';
  PreviewSize: Int64 = 0;
  PreviewFirmware: string = '';
  PreviewCode: Integer = 0;
  PreviewHasCode: Boolean = False;

{ ---- harness ---- }

procedure Pass(const Name: string);
begin
  Inc(Checks);
end;

procedure Fail(const Name, Detail: string);
begin
  Inc(Checks);
  Inc(Failures);
  WriteLn('FAIL ', Name);
  if Detail <> '' then
    WriteLn('     ', Detail);
end;

function FrameOf(const Lines: array of string): TStringArray;
var
  I: Integer;
begin
  SetLength(Result, Length(Lines));
  for I := 0 to High(Lines) do
    Result[I] := Lines[I];
end;

function KeysOf(const Keys: array of string): TStringArray;
var
  I: Integer;
begin
  SetLength(Result, Length(Keys));
  for I := 0 to High(Keys) do
    Result[I] := Keys[I];
end;

function EventName(E: TEvent): string;
begin
  case E of
    evIgnore: Result := 'evIgnore';
    evSelectUp: Result := 'evSelectUp';
    evSelectDown: Result := 'evSelectDown';
    evAdvance: Result := 'evAdvance';
    evQuit: Result := 'evQuit';
    evSetUefi: Result := 'evSetUefi';
    evSetBios: Result := 'evSetBios';
    evCancel: Result := 'evCancel';
    evAppend: Result := 'evAppend';
    evBackspace: Result := 'evBackspace';
    evAccept: Result := 'evAccept';
    evPreviewOk: Result := 'evPreviewOk';
    evPreviewFailed: Result := 'evPreviewFailed';
  end;
end;

function StateName(S: TState): string;
begin
  case S of
    stNoDisks: Result := 'stNoDisks';
    stDiskChoice: Result := 'stDiskChoice';
    stFirmware: Result := 'stFirmware';
    stConfirm: Result := 'stConfirm';
    stPreviewing: Result := 'stPreviewing';
    stPreviewError: Result := 'stPreviewError';
    stDone: Result := 'stDone';
    stMismatch: Result := 'stMismatch';
    stLeave: Result := 'stLeave';
  end;
end;

procedure ExpectInt(const Name: string; Actual, Expected: Integer);
begin
  if Actual = Expected then
    Pass(Name)
  else
    Fail(Name, 'expected ' + IntToStr(Expected) + ' | actual ' +
      IntToStr(Actual));
end;

procedure ExpectStr(const Name, Actual, Expected: string);
begin
  if Actual = Expected then
    Pass(Name)
  else
    Fail(Name, 'expected ' + Expected + ' | actual ' + Actual);
end;

procedure ExpectEvent(const Name: string; Actual: TEvent;
  const Expected: string);
begin
  if EventName(Actual) = Expected then
    Pass(Name)
  else
    Fail(Name, 'expected ' + Expected + ' | actual ' + EventName(Actual));
end;

procedure ExpectState(const Name: string; Actual: TState;
  const Expected: string);
begin
  if StateName(Actual) = Expected then
    Pass(Name)
  else
    Fail(Name, 'expected ' + Expected + ' | actual ' + StateName(Actual));
end;

procedure ExpectFrame(const Name: string; const Actual,
  Expected: TStringArray);
var
  I: Integer;
begin
  if Length(Actual) <> Length(Expected) then
  begin
    Fail(Name, 'line count ' + IntToStr(Length(Actual)) + ' vs ' +
      IntToStr(Length(Expected)));
    Exit;
  end;
  for I := 0 to High(Expected) do
    if Actual[I] <> Expected[I] then
    begin
      Fail(Name + ' line ' + IntToStr(I),
        'expected ' + Expected[I] + ' | actual ' + Actual[I]);
      Exit;
    end;
  Pass(Name);
end;

{ The preview callback the flow calls. Returns whatever the current scenario
  set up, and records the arguments so the call itself can be asserted. }
function PreviewRecord(const Path: string; SizeBytes: Int64;
  const Firmware: string): TPreviewResult;
begin
  Inc(PreviewCalls);
  PreviewPath := Path;
  PreviewSize := SizeBytes;
  PreviewFirmware := Firmware;
  Result.HasCode := PreviewHasCode;
  Result.Code := PreviewCode;
end;

procedure ResetPreview;
begin
  PreviewCalls := 0;
  PreviewPath := '';
  PreviewSize := 0;
  PreviewFirmware := '';
  PreviewHasCode := False;
  PreviewCode := 0;
end;

{ ---- 1. key -> event ---- }

procedure CheckKeys;
var
  K: TKey;
begin
  ExpectEvent('stDiskChoice ''q'' -> quit', Transition(stDiskChoice, 'q'), 'evQuit');
  ExpectEvent('stDiskChoice ''й'' -> quit', Transition(stDiskChoice, 'й'), 'evQuit');
  ExpectEvent('stDiskChoice ''quit'' -> quit', Transition(stDiskChoice, 'quit'), 'evQuit');
  ExpectEvent('stDiskChoice ''up'' -> up', Transition(stDiskChoice, 'up'), 'evSelectUp');
  ExpectEvent('stDiskChoice ''k'' -> up', Transition(stDiskChoice, 'k'), 'evSelectUp');
  ExpectEvent('stDiskChoice ''л'' -> up', Transition(stDiskChoice, 'л'), 'evSelectUp');
  ExpectEvent('stDiskChoice ''down'' -> down', Transition(stDiskChoice, 'down'), 'evSelectDown');
  ExpectEvent('stDiskChoice ''j'' -> down', Transition(stDiskChoice, 'j'), 'evSelectDown');
  ExpectEvent('stDiskChoice ''о'' -> down', Transition(stDiskChoice, 'о'), 'evSelectDown');
  ExpectEvent('stDiskChoice ''o'' latin is not a key', Transition(stDiskChoice, 'o'), 'evIgnore');
  ExpectEvent('stDiskChoice ''l'' latin is not a key', Transition(stDiskChoice, 'l'), 'evIgnore');
  ExpectEvent('stDiskChoice ''enter'' -> advance', Transition(stDiskChoice, 'enter'), 'evAdvance');
  ExpectEvent('stDiskChoice CR -> advance', Transition(stDiskChoice, #13), 'evAdvance');
  ExpectEvent('stDiskChoice ''esc'' -> ignored', Transition(stDiskChoice, 'esc'), 'evIgnore');
  ExpectEvent('stDiskChoice ''1'' -> ignored', Transition(stDiskChoice, '1'), 'evIgnore');
  ExpectEvent('stFirmware ''1'' -> uefi', Transition(stFirmware, '1'), 'evSetUefi');
  ExpectEvent('stFirmware ''2'' -> bios', Transition(stFirmware, '2'), 'evSetBios');
  ExpectEvent('stFirmware ''up'' -> uefi', Transition(stFirmware, 'up'), 'evSetUefi');
  ExpectEvent('stFirmware ''down'' -> bios', Transition(stFirmware, 'down'), 'evSetBios');
  ExpectEvent('stFirmware ''k'' -> uefi', Transition(stFirmware, 'k'), 'evSetUefi');
  ExpectEvent('stFirmware ''j'' -> bios', Transition(stFirmware, 'j'), 'evSetBios');
  ExpectEvent('stFirmware ''enter'' -> advance', Transition(stFirmware, 'enter'), 'evAdvance');
  ExpectEvent('stFirmware ''q'' -> quit', Transition(stFirmware, 'q'), 'evQuit');
  ExpectEvent('stFirmware ''3'' -> ignored', Transition(stFirmware, '3'), 'evIgnore');
  ExpectEvent('stConfirm ''esc'' -> cancel', Transition(stConfirm, 'esc'), 'evCancel');
  ExpectEvent('stConfirm ''enter'' -> accept', Transition(stConfirm, 'enter'), 'evAccept');
  ExpectEvent('stConfirm CR is not accept', Transition(stConfirm, #13), 'evIgnore');
  ExpectEvent('stConfirm DEL -> backspace', Transition(stConfirm, #127), 'evBackspace');
  ExpectEvent('stConfirm ''backspace'' -> backspace', Transition(stConfirm, 'backspace'), 'evBackspace');
  ExpectEvent('stConfirm ''/'' -> append', Transition(stConfirm, '/'), 'evAppend');
  ExpectEvent('stConfirm ''q'' is a path char, not quit', Transition(stConfirm, 'q'), 'evAppend');
  ExpectEvent('stConfirm ''j'' is a path char, not down', Transition(stConfirm, 'j'), 'evAppend');
  ExpectEvent('stConfirm ''й'' is a path char', Transition(stConfirm, 'й'), 'evAppend');
  ExpectEvent('stConfirm ''quit'' is not a command', Transition(stConfirm, 'quit'), 'evIgnore');
  ExpectEvent('stConfirm ''up'' is not a command', Transition(stConfirm, 'up'), 'evIgnore');
  ExpectEvent('stNoDisks any key -> quit', Transition(stNoDisks, 'x'), 'evQuit');
  ExpectEvent('stMismatch any key -> quit', Transition(stMismatch, 'enter'), 'evQuit');

  K := NormalizeKey('/');
  ExpectStr('normalize_key keeps a path character', K.Ch, '/');
  K := NormalizeKey('о');
  ExpectStr('normalize_key maps the Ukrainian down key', K.Ch, 'о');
  K := NormalizeKey('q');
  ExpectEvent('normalize_key maps q to quit', Transition(stDiskChoice,
    K.Ch), 'evQuit');
end;

{ ---- 2. state table ---- }

procedure CheckStates;
begin
  ExpectState('stNoDisks -> leave', NextState(stNoDisks, evQuit, False), 'stLeave');
  ExpectState('stDiskChoice + quit -> leave', NextState(stDiskChoice, evQuit, False), 'stLeave');
  ExpectState('stDiskChoice + advance -> firmware', NextState(stDiskChoice, evAdvance, False), 'stFirmware');
  ExpectState('stDiskChoice + up stays', NextState(stDiskChoice, evSelectUp, False), 'stDiskChoice');
  ExpectState('stFirmware + advance -> confirm', NextState(stFirmware, evAdvance, False), 'stConfirm');
  ExpectState('stFirmware + quit -> leave', NextState(stFirmware, evQuit, False), 'stLeave');
  ExpectState('stConfirm + cancel -> leave', NextState(stConfirm, evCancel, False), 'stLeave');
  ExpectState('stConfirm + accept, match -> previewing', NextState(stConfirm, evAccept, True), 'stPreviewing');
  ExpectState('stConfirm + accept, mismatch -> mismatch', NextState(stConfirm, evAccept, False), 'stMismatch');
  ExpectState('stConfirm + append stays', NextState(stConfirm, evAppend, False), 'stConfirm');
  ExpectState('stPreviewing ok -> done', NextState(stPreviewing, evPreviewOk, False), 'stDone');
  ExpectState('stPreviewing failed -> preview error', NextState(stPreviewing, evPreviewFailed, False), 'stPreviewError');
  ExpectState('stDone -> leave', NextState(stDone, evQuit, False), 'stLeave');
  ExpectState('stPreviewError -> leave', NextState(stPreviewError, evQuit, False), 'stLeave');
end;

{ ---- 3. layout primitives ---- }

procedure CheckLayout;
var
  B: TStringArray;
begin
  ExpectInt('Utf8Length of an empty string', Utf8Length(''), 0);
  ExpectInt('Utf8Length ascii', Utf8Length('/dev/sda'), 8);
  ExpectInt('Utf8Length cyrillic counts characters', Utf8Length('знімний'), 7);
  ExpectStr('Utf8Copy keeps the whole string', Utf8Copy('/dev/sda', 8), '/dev/sda');
  ExpectStr('Utf8Copy cuts the confirmation line at 58', Utf8Copy('Диск не змінюватиметься. Введіть його шлях; Esc — скасувати.', 58), 'Диск не змінюватиметься. Введіть його шлях; Esc — скасуват');
  ExpectStr('Utf8Copy past the end returns the string', Utf8Copy('abc', 10), 'abc');
  ExpectStr('Utf8PadRight pads by characters', Utf8PadRight('знімний', 9), 'знімний  ');
  ExpectStr('HumanSize GiB', HumanSize(274877906944), '256 GiB');
  ExpectStr('HumanSize GiB 120', HumanSize(128849018880), '120 GiB');
  ExpectStr('HumanSize MiB below one GiB', HumanSize(536870912), '512 MiB');

  { box() is rectangular for every frame below; this is the same invariant
    tests/test_tui.py asserts, on a line that has to be truncated. }
  B := Box('T', FrameOf(['x' + RepeatStr('y', 500)]));
  ExpectInt('box has 5 lines for one body line', Length(B), 5);
  ExpectInt('box truncates instead of wrapping', Utf8Length(B[3]), BOX_WIDTH);
  ExpectInt('box is rectangular', Utf8Length(B[0]), BOX_WIDTH);
  ExpectInt('box pads the title line', Utf8Length(B[1]), BOX_WIDTH);
end;

{ ---- 4. whole sessions ---- }

procedure CheckInitial;
var
  Scr: TScriptedScreen;
  Screen: IScreen;
  Code: Integer;
  Disks: TCandidates;
begin
  ResetPreview;
  SetLength(Disks, 2);
  Disks[0].Path := '/dev/nvme0n1';
  Disks[0].SizeBytes := 274877906944;
  Disks[0].IsRemovable := False;
  Disks[1].Path := '/dev/sda';
  Disks[1].SizeBytes := 128849018880;
  Disks[1].IsRemovable := True;
  Scr := TScriptedScreen.CreateScripted(KeysOf([
      'q'
    ]));
  Screen := Scr;
  Code := RunTui(Screen, Disks, @PreviewRecord, '');
  ExpectInt('initial_quit exit code', Code, 1);
  ExpectInt('initial_quit frame count', Scr.FrameCount, 1);
  ExpectInt('initial_quit preview calls', PreviewCalls, 0);
  ExpectFrame('initial_quit frame 0', Scr.Frame(0), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ WSM • перегляд плану                                       │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Оберіть диск для перегляду плану:                          │',
    '│                                                            │',
    '│ > 1. /dev/nvme0n1       256 GiB                            │',
    '│   2. /dev/sda           120 GiB  знімний                   │',
    '│                                                            │',
    '│ ↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  Screen := nil;   { releases the scripted screen, so keep it until here }
end;

procedure CheckNavigation;
var
  Scr: TScriptedScreen;
  Screen: IScreen;
  Code: Integer;
  Disks: TCandidates;
begin
  ResetPreview;
  SetLength(Disks, 2);
  Disks[0].Path := '/dev/nvme0n1';
  Disks[0].SizeBytes := 274877906944;
  Disks[0].IsRemovable := False;
  Disks[1].Path := '/dev/sda';
  Disks[1].SizeBytes := 128849018880;
  Disks[1].IsRemovable := True;
  Scr := TScriptedScreen.CreateScripted(KeysOf([
      'down',
      'down',
      'up',
      'q'
    ]));
  Screen := Scr;
  Code := RunTui(Screen, Disks, @PreviewRecord, '');
  ExpectInt('navigation exit code', Code, 1);
  ExpectInt('navigation frame count', Scr.FrameCount, 4);
  ExpectInt('navigation preview calls', PreviewCalls, 0);
  ExpectFrame('navigation frame 0', Scr.Frame(0), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ WSM • перегляд плану                                       │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Оберіть диск для перегляду плану:                          │',
    '│                                                            │',
    '│ > 1. /dev/nvme0n1       256 GiB                            │',
    '│   2. /dev/sda           120 GiB  знімний                   │',
    '│                                                            │',
    '│ ↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('navigation frame 1', Scr.Frame(1), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ WSM • перегляд плану                                       │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Оберіть диск для перегляду плану:                          │',
    '│                                                            │',
    '│   1. /dev/nvme0n1       256 GiB                            │',
    '│ > 2. /dev/sda           120 GiB  знімний                   │',
    '│                                                            │',
    '│ ↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('navigation frame 2', Scr.Frame(2), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ WSM • перегляд плану                                       │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Оберіть диск для перегляду плану:                          │',
    '│                                                            │',
    '│ > 1. /dev/nvme0n1       256 GiB                            │',
    '│   2. /dev/sda           120 GiB  знімний                   │',
    '│                                                            │',
    '│ ↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('navigation frame 3', Scr.Frame(3), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ WSM • перегляд плану                                       │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Оберіть диск для перегляду плану:                          │',
    '│                                                            │',
    '│   1. /dev/nvme0n1       256 GiB                            │',
    '│ > 2. /dev/sda           120 GiB  знімний                   │',
    '│                                                            │',
    '│ ↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  Screen := nil;   { releases the scripted screen, so keep it until here }
end;

procedure CheckConfirmEsc;
var
  Scr: TScriptedScreen;
  Screen: IScreen;
  Code: Integer;
  Disks: TCandidates;
begin
  ResetPreview;
  SetLength(Disks, 2);
  Disks[0].Path := '/dev/nvme0n1';
  Disks[0].SizeBytes := 274877906944;
  Disks[0].IsRemovable := False;
  Disks[1].Path := '/dev/sda';
  Disks[1].SizeBytes := 128849018880;
  Disks[1].IsRemovable := True;
  Scr := TScriptedScreen.CreateScripted(KeysOf([
      'enter',
      'enter',
      'esc'
    ]));
  Screen := Scr;
  Code := RunTui(Screen, Disks, @PreviewRecord, '');
  ExpectInt('confirm_esc exit code', Code, 1);
  ExpectInt('confirm_esc frame count', Scr.FrameCount, 3);
  ExpectInt('confirm_esc preview calls', PreviewCalls, 0);
  ExpectFrame('confirm_esc frame 0', Scr.Frame(0), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ WSM • перегляд плану                                       │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Оберіть диск для перегляду плану:                          │',
    '│                                                            │',
    '│ > 1. /dev/nvme0n1       256 GiB                            │',
    '│   2. /dev/sda           120 GiB  знімний                   │',
    '│                                                            │',
    '│ ↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('confirm_esc frame 1', Scr.Frame(1), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Режим завантаження                                         │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Диск: /dev/nvme0n1  (256 GiB)                              │',
    '│                                                            │',
    '│   [1] UEFI  <-                                             │',
    '│   [2] BIOS                                                 │',
    '│                                                            │',
    '│ 1/2 або стрілки — змінити; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('confirm_esc frame 2', Scr.Frame(2), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > _                                                      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  Screen := nil;   { releases the scripted screen, so keep it until here }
end;

procedure CheckRefusal;
var
  Scr: TScriptedScreen;
  Screen: IScreen;
  Code: Integer;
  Disks: TCandidates;
begin
  ResetPreview;
  SetLength(Disks, 2);
  Disks[0].Path := '/dev/nvme0n1';
  Disks[0].SizeBytes := 274877906944;
  Disks[0].IsRemovable := False;
  Disks[1].Path := '/dev/sda';
  Disks[1].SizeBytes := 128849018880;
  Disks[1].IsRemovable := True;
  Scr := TScriptedScreen.CreateScripted(KeysOf([
      'enter',
      'enter',
      '/',
      'd',
      'e',
      'v',
      '/',
      's',
      'd',
      'a',
      'enter',
      'q'
    ]));
  Screen := Scr;
  Code := RunTui(Screen, Disks, @PreviewRecord, '');
  ExpectInt('refusal_wrong_path exit code', Code, 1);
  ExpectInt('refusal_wrong_path frame count', Scr.FrameCount, 12);
  ExpectInt('refusal_wrong_path preview calls', PreviewCalls, 0);
  ExpectFrame('refusal_wrong_path frame 0', Scr.Frame(0), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ WSM • перегляд плану                                       │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Оберіть диск для перегляду плану:                          │',
    '│                                                            │',
    '│ > 1. /dev/nvme0n1       256 GiB                            │',
    '│   2. /dev/sda           120 GiB  знімний                   │',
    '│                                                            │',
    '│ ↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 1', Scr.Frame(1), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Режим завантаження                                         │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Диск: /dev/nvme0n1  (256 GiB)                              │',
    '│                                                            │',
    '│   [1] UEFI  <-                                             │',
    '│   [2] BIOS                                                 │',
    '│                                                            │',
    '│ 1/2 або стрілки — змінити; Enter — далі; q/й — вихід.      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 2', Scr.Frame(2), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > _                                                      │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 3', Scr.Frame(3), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /_                                                     │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 4', Scr.Frame(4), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /d_                                                    │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 5', Scr.Frame(5), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /de_                                                   │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 6', Scr.Frame(6), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /dev_                                                  │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 7', Scr.Frame(7), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /dev/_                                                 │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 8', Scr.Frame(8), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /dev/s_                                                │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 9', Scr.Frame(9), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /dev/sd_                                               │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 10', Scr.Frame(10), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Підтвердження                                              │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Ціль перегляду: /dev/nvme0n1 (256 GiB).                    │',
    '│                                                            │',
    '│ Диск не змінюватиметься. Введіть його шлях; Esc — скасуват │',
    '│                                                            │',
    '│   > /dev/sda_                                              │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  ExpectFrame('refusal_wrong_path frame 11', Scr.Frame(11), FrameOf([
    '┌────────────────────────────────────────────────────────────┐',
    '│ Зупинено                                                   │',
    '├────────────────────────────────────────────────────────────┤',
    '│                                                            │',
    '│ Введений шлях не збігається з обраним диском.              │',
    '│ Змін не внесено.                                           │',
    '└────────────────────────────────────────────────────────────┘'
  ]));
  Screen := nil;   { releases the scripted screen, so keep it until here }
end;

begin
  CheckKeys;
  CheckStates;
  CheckLayout;
  CheckInitial;
  CheckNavigation;
  CheckConfirmEsc;
  CheckRefusal;

  WriteLn(IntToStr(Checks), ' checks, ', IntToStr(Failures), ' failures');
  if Failures <> 0 then
    Halt(1);
end.
