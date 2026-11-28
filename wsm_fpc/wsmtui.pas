unit wsmtui;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Terminal slice of the FPC port.

  Reproduces wsm_install/tui.py: the pseudo-graphic preview UI of the
  minimal-live path. The Python module is already split the right way - drawing
  is a list of strings and input is an injected reader - and this unit keeps
  that split and sharpens it:

    * layout is a function of a state record (TView), so a frame can be compared
      against a golden vector without a terminal;
    * key handling is one function (Transition) from (state, key) to an event,
      so the state table is data, not control flow;
    * the state machine is one function (NextState) from (state, event, match) to
      state, so every edge is testable on its own;
    * the driver (RunTui) talks only to IScreen: two calls, Render and ReadKey.
      A scripted screen drives the whole flow; the real terminal is one
      implementation of that interface and nothing above it knows.

  The unit holds the flow, not the decisions behind it. Two gates look like
  decisions here and are not:

    * the firmware value is only ever 'uefi' or 'bios' because the state has no
      other reachable value; the authority on whether a firmware string is legal
      is wsmplan.ValidateTarget (CODE_DISK_FIRMWARE), which also owns the
      whole-device check, the running-system check, the size floor and the
      acknowledgement rule;
    * the typed-path comparison (TargetMatches) is a UI pre-check that produces
      the "Зупинено" screen. The authoritative acknowledgement rule is
      wsmplan.ValidateTarget (CODE_DISK_ACKNOWLEDGEMENT). If this unit and that
      one ever disagree, that one is right.

  Layout arithmetic is over UTF-8 CODE POINTS, not bytes, because the Python box
  pads and truncates characters: "Диск не змінюватиметься..." is cut at 58
  characters mid-word, and a byte-wise ljust would make the frame ragged. Every
  string in this unit is UTF-8 and Length() is a byte count, so Utf8Length and
  Utf8Copy exist and are used everywhere a Python slice or ljust appears.

  Not compiled here: no FPC in this environment. The vectors in
  wsmtui_vectors.pas were captured by running the Python TUI. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

const
  { Python: BOX_WIDTH = 62. The frames are exactly this many characters wide and
    the TUI assumes a terminal at least that wide. }
  BOX_WIDTH = 62;
  CLEAR_SEQ = #27 + '[2J' + #27 + '[H';
  { Declared by the Python module and never emitted; kept so a future adapter can
    use them without touching this unit. }
  HIDE_CURSOR = #27 + '[?25l';
  SHOW_CURSOR = #27 + '[?25h';

type
  TStringArray = array of string;

  { Mirrors wsm_install.guided.Candidate, restricted to what the screen shows. }
  TCandidate = record
    Path: string;
    SizeBytes: Int64;
    IsRemovable: Boolean;
  end;
  TCandidates = array of TCandidate;

  { A key as the pure layer sees it. The adapter decides which byte sequence
    means which of these; nothing below looks at bytes. }
  TKeyKind = (kkChar, kkEnter, kkUp, kkDown, kkQuit, kkEsc);
  TKey = record
    Kind: TKeyKind;
    { Only meaningful for kkChar. A character is a UTF-8 string, not a Char:
      'й' is two bytes. }
    Ch: string;
  end;

  TState = (stNoDisks, stDiskChoice, stFirmware, stConfirm,
            stPreviewing, stPreviewError, stDone, stMismatch, stLeave);

  TEvent = (evIgnore, evSelectUp, evSelectDown, evAdvance, evQuit,
            evSetUefi, evSetBios, evCancel, evAppend, evBackspace, evAccept,
            evPreviewOk, evPreviewFailed);

  { Everything a frame depends on, in one record: RenderView is a function of
    this and of nothing else. }
  TView = record
    State: TState;
    Disks: TCandidates;
    Selected: Integer;
    Firmware: string;
    Typed: string;
    EvidenceNote: string;
    PreviewCode: Integer;
  end;

  { The narrow interface the terminal sits behind. No cursor control, no size
    query, no colour: the only two things the flow needs. }
  IScreen = interface
    procedure Render(const Lines: TStringArray);
    function ReadKey: string;
  end;

  { Python's preview() returns object; an int means "exit code", anything else
    means success. HasCode carries that distinction rather than guessing from a
    zero. }
  TPreviewResult = record
    HasCode: Boolean;
    Code: Integer;
  end;
  TPreviewProc = function(const Path: string; SizeBytes: Int64;
    const Firmware: string): TPreviewResult;

{ ---- layout: pure ---- }
function Utf8Length(const S: string): Integer;
function Utf8Copy(const S: string; Count: Integer): string;
function Utf8CodePoint(const S: string): LongWord;
function Utf8Printable(const S: string): Boolean;
function RepeatStr(const S: string; Count: Integer): string;
function Utf8PadRight(const S: string; Width: Integer): string;
function Utf8PadLeft(const S: string; Width: Integer): string;
function HumanSize(SizeBytes: Int64): string;
function Box(const Title: string; const Body: TStringArray): TStringArray;
function BoxWidth(const Title: string; const Body: TStringArray;
  Width: Integer): TStringArray;
function DiskList(const Disks: TCandidates; Selected: Integer): TStringArray;
function RenderView(const View: TView): TStringArray;

{ ---- keys and transitions: pure ---- }
function KeyChar(const Ch: string): TKey;
function NormalizeKey(const Token: string): TKey;
function Transition(const State: TState; const Raw: string): TEvent;
function NextState(const State: TState; Event: TEvent;
  TargetMatches: Boolean): TState;
function TargetMatches(const Typed, Path: string): Boolean;

{ ---- driver: one loop, and it only talks to IScreen ---- }
function RunTui(const Screen: IScreen; const Disks: TCandidates;
  const Preview: TPreviewProc; const EvidenceNote: string): Integer;

implementation

{ ---- UTF-8 helpers ----

  Python indexes and slices str by code point; FPC indexes an AnsiString by
  byte. Every place the Python code does entry[:inner], ljust, :>9 or typed[:-1]
  goes through these four functions. }

function Utf8Length(const S: string): Integer;
var
  I, N: Integer;
begin
  Result := 0;
  I := 1;
  N := Length(S);
  while I <= N do
  begin
    Inc(Result);
    { Skip the continuation bytes of this code point. }
    while (I < N) and ((Ord(S[I + 1]) and $C0) = $80) do
      Inc(I);
    Inc(I);
  end;
end;

function Utf8Copy(const S: string; Count: Integer): string;
var
  I, N, Seen: Integer;
begin
  if Count <= 0 then
    Exit('');
  N := Length(S);
  Seen := 0;
  I := 1;
  while (I <= N) and (Seen < Count) do
  begin
    Inc(Seen);
    while (I < N) and ((Ord(S[I + 1]) and $C0) = $80) do
      Inc(I);
    Inc(I);
  end;
  if I > N then
    Result := S
  else
    Result := Copy(S, 1, I - 1);
end;

function Utf8CodePoint(const S: string): LongWord;
begin
  Result := 0;
  if Length(S) = 0 then
    Exit;
  if Length(S) = 1 then
    Result := Ord(S[1])
  else if (Length(S) = 2) and ((Ord(S[1]) and $E0) = $C0) then
    Result := ((Ord(S[1]) and $1F) shl 6) or (Ord(S[2]) and $3F)
  else if (Length(S) = 3) and ((Ord(S[1]) and $F0) = $E0) then
    Result := ((Ord(S[1]) and $0F) shl 12) or ((Ord(S[2]) and $3F) shl 6) or
              (Ord(S[3]) and $3F)
  else if (Length(S) = 4) and ((Ord(S[1]) and $F8) = $F0) then
    Result := ((Ord(S[1]) and $07) shl 18) or ((Ord(S[2]) and $3F) shl 12) or
              ((Ord(S[3]) and $3F) shl 6) or (Ord(S[4]) and $3F)
  else
    Result := Ord(S[1]);
end;

{ Python str.isprintable: a space is printable, C0, DEL and C1 controls are not. }
function Utf8Printable(const S: string): Boolean;
var
  CP: LongWord;
begin
  CP := Utf8CodePoint(S);
  Result := (CP >= $20) and (CP <> $7F) and not ((CP >= $80) and (CP <= $9F));
end;

function RepeatStr(const S: string; Count: Integer): string;
var
  I: Integer;
begin
  Result := '';
  for I := 1 to Count do
    Result := Result + S;
end;

function Utf8PadRight(const S: string; Width: Integer): string;
var
  Pad: Integer;
begin
  Pad := Width - Utf8Length(S);
  if Pad <= 0 then
    Result := S
  else
    Result := S + RepeatStr(' ', Pad);
end;

function Utf8PadLeft(const S: string; Width: Integer): string;
var
  Pad: Integer;
begin
  Pad := Width - Utf8Length(S);
  if Pad <= 0 then
    Result := S
  else
    Result := RepeatStr(' ', Pad) + S;
end;

{ Python the Python format spec with zero decimals rounds half to even; FormatFloat does not promise that,
  and a disk size that lands exactly on .5 GiB must not gain or lose a GiB
  between the two implementations. }
function PyFixed0(const V: Double): string;
var
  Whole: Double;
  Frac: Double;
  N: Int64;
begin
  Whole := Int(V);
  Frac := V - Whole;
  N := Trunc(Whole);
  if Frac > 0.5 then
    Inc(N)
  else if (Frac = 0.5) and Odd(N) then
    Inc(N);
  Result := IntToStr(N);
end;

{ guided.Candidate.human_size, byte for byte. }
function HumanSize(SizeBytes: Int64): string;
var
  Gib: Double;
begin
  Gib := SizeBytes / (1024.0 * 1024.0 * 1024.0);
  if Gib >= 1 then
    Result := PyFixed0(Gib) + ' GiB'
  else
    Result := PyFixed0(SizeBytes / (1024.0 * 1024.0)) + ' MiB';
end;

function BoxWidth(const Title: string; const Body: TStringArray;
  Width: Integer): TStringArray;
var
  Inner, I, N: Integer;
  Rule: string;
begin
  { Python: inner = max(width - 4, 10) }
  Inner := Width - 4;
  if Inner < 10 then
    Inner := 10;
  Rule := RepeatStr('─', Width - 2);
  N := Length(Body);
  SetLength(Result, N + 4);
  Result[0] := '┌' + Rule + '┐';
  Result[1] := '│ ' + Utf8PadRight(Utf8Copy(Title, Inner), Inner) + ' │';
  Result[2] := '├' + Rule + '┤';
  for I := 0 to N - 1 do
    Result[3 + I] := '│ ' + Utf8PadRight(Utf8Copy(Body[I], Inner), Inner) + ' │';
  Result[N + 3] := '└' + Rule + '┘';
end;

function Box(const Title: string; const Body: TStringArray): TStringArray;
begin
  Result := BoxWidth(Title, Body, BOX_WIDTH);
end;

{ Row layout: marker, index, left-padded path, right-padded size, removable flag.
  Written out in the comment rather than quoted, because a literal brace inside a
  Pascal comment ends it early. }
function DiskList(const Disks: TCandidates; Selected: Integer): TStringArray;
var
  I: Integer;
  Marker, Removable: string;
begin
  SetLength(Result, Length(Disks));
  for I := 0 to High(Disks) do
  begin
    if I = Selected then
      Marker := '>'
    else
      Marker := ' ';
    if Disks[I].IsRemovable then
      Removable := '  знімний'
    else
      Removable := '';
    Result[I] := Marker + ' ' + IntToStr(I + 1) + '. ' +
                 Utf8PadRight(Disks[I].Path, 16) + ' ' +
                 Utf8PadLeft(HumanSize(Disks[I].SizeBytes), 9) + Removable;
  end;
end;

function AppendLine(var Lines: TStringArray; const S: string);
begin
  SetLength(Lines, Length(Lines) + 1);
  Lines[High(Lines)] := S;
end;

{ One frame per state, exactly as run_tui builds it inline. }
function RenderView(const View: TView): TStringArray;
var
  Body, List: TStringArray;
  Disk: TCandidate;
  I: Integer;
  Title: string;
begin
  if (View.Selected >= 0) and (View.Selected <= High(View.Disks)) then
    Disk := View.Disks[View.Selected]
  else
  begin
    Disk.Path := '';
    Disk.SizeBytes := 0;
    Disk.IsRemovable := False;
  end;

  Body := nil;

  case View.State of
    stNoDisks:
      begin
        Title := 'WSM • перегляд плану';
        AppendLine(Body, 'Дисків для перегляду не знайдено.');
        AppendLine(Body, 'Перевірте, чи система бачить диск: lsblk');
        AppendLine(Body, '');
        AppendLine(Body, 'Натисніть q (або й), щоб вийти.');
      end;

    stDiskChoice:
      begin
        Title := 'WSM • перегляд плану';
        AppendLine(Body, '');
        AppendLine(Body, 'Оберіть диск для перегляду плану:');
        AppendLine(Body, '');
        List := DiskList(View.Disks, View.Selected);
        for I := 0 to High(List) do
          AppendLine(Body, List[I]);
        AppendLine(Body, '');
        AppendLine(Body, '↑/↓ або j/k (о/л) — вибір; Enter — далі; q/й — вихід.');
        if View.EvidenceNote <> '' then
        begin
          AppendLine(Body, '');
          { Truncated twice in Python - here and in box() - with the same width. }
          AppendLine(Body, Utf8Copy('Обладнання: ' + View.EvidenceNote,
            BOX_WIDTH - 4));
        end;
      end;

    stFirmware:
      begin
        Title := 'Режим завантаження';
        AppendLine(Body, '');
        AppendLine(Body, 'Диск: ' + Disk.Path + '  (' +
          HumanSize(Disk.SizeBytes) + ')');
        AppendLine(Body, '');
        if View.Firmware = 'uefi' then
          AppendLine(Body, '  [1] UEFI  <-')
        else
          AppendLine(Body, '  [1] UEFI');
        if View.Firmware = 'bios' then
          AppendLine(Body, '  [2] BIOS  <-')
        else
          AppendLine(Body, '  [2] BIOS');
        AppendLine(Body, '');
        AppendLine(Body, '1/2 або стрілки — змінити; Enter — далі; q/й — вихід.');
      end;

    stConfirm:
      begin
        Title := 'Підтвердження';
        AppendLine(Body, '');
        AppendLine(Body, 'Ціль перегляду: ' + Disk.Path + ' (' +
          HumanSize(Disk.SizeBytes) + ').');
        AppendLine(Body, '');
        AppendLine(Body, 'Диск не змінюватиметься. Введіть його шлях; Esc — скасувати.');
        AppendLine(Body, '');
        AppendLine(Body, '  > ' + View.Typed + '_');
      end;

    stPreviewing:
      begin
        Title := 'Перегляд';
        AppendLine(Body, '');
        AppendLine(Body, 'Готуємо попередній перегляд ' + Disk.Path +
          ' лише для читання...');
      end;

    stPreviewError:
      begin
        Title := 'Помилка перегляду';
        AppendLine(Body, '');
        AppendLine(Body, 'Не вдалося створити перегляд (код ' +
          IntToStr(View.PreviewCode) + ').');
        AppendLine(Body, 'APPLY вимкнено. Змін не внесено.');
      end;

    stDone:
      begin
        Title := 'Перегляд завершено';
        AppendLine(Body, '');
        AppendLine(Body, 'План підготовлено для ' + Disk.Path + ' (' +
          View.Firmware + ').');
        AppendLine(Body, '');
        AppendLine(Body, 'APPLY вимкнено.');
        AppendLine(Body, 'Команди роботи з диском не виконувалися.');
        AppendLine(Body, 'WSM НЕ встановлено.');
      end;

    stMismatch:
      begin
        Title := 'Зупинено';
        AppendLine(Body, '');
        AppendLine(Body, 'Введений шлях не збігається з обраним диском.');
        AppendLine(Body, 'Змін не внесено.');
      end;
  else
  begin
    { stLeave renders nothing; the driver never asks. }
    Result := nil;
    Exit;
  end;
  end;

  Result := Box(Title, Body);
end;

{ ---- keys ---- }

function KeyChar(const Ch: string): TKey;
begin
  Result.Kind := kkChar;
  Result.Ch := Ch;
end;

{ normalize_key: the US and Ukrainian layouts share the shortcuts. Note what is
  not here: Latin 'o' and 'l' are not navigation keys, only 'j'/'k' and the
  Cyrillic 'о'/'л' are, and a literal 'quit' is accepted so a scripted screen can
  spell the action out the way tests/test_tui.py does. }
function NormalizeKey(const Token: string): TKey;
begin
  Result := KeyChar(Token);
  if (Token = #13) or (Token = #10) or (Token = 'enter') then
    Result.Kind := kkEnter
  else if Token = 'up' then
    Result.Kind := kkUp
  else if Token = 'down' then
    Result.Kind := kkDown
  else if Token = 'esc' then
    Result.Kind := kkEsc
  else if (Token = 'q') or (Token = 'й') or (Token = 'quit') then
    Result.Kind := kkQuit
  else if (Token = 'k') or (Token = 'л') then
    Result.Kind := kkUp
  else if (Token = 'j') or (Token = 'о') then
    Result.Kind := kkDown;
end;

{ One function from (state, key token) to an action. The two screens that exist
  only to be acknowledged swallow any key; the confirmation screen is the one
  place where the shortcut letters are ordinary characters, so it is handled
  before normalize_key is applied - a device path may be /dev/sdq. }
function Transition(const State: TState; const Raw: string): TEvent;
var
  Key: TKey;
begin
  if (State = stNoDisks) or (State = stMismatch) then
    Exit(evQuit);

  if State = stConfirm then
  begin
    { Only the tokens the adapter produces: 'esc' and 'enter' are named, never
      the raw CR, because a CR inside a path is not a confirmation. }
    if Raw = 'esc' then
      Exit(evCancel);
    if Raw = 'enter' then
      Exit(evAccept);
    if (Raw = #127) or (Raw = 'backspace') then
      Exit(evBackspace);
    if (Utf8Length(Raw) = 1) and Utf8Printable(Raw) then
      Exit(evAppend);
    Exit(evIgnore);
  end;

  Key := NormalizeKey(Raw);

  if State = stDiskChoice then
  begin
    case Key.Kind of
      kkQuit: Exit(evQuit);
      kkUp: Exit(evSelectUp);
      kkDown: Exit(evSelectDown);
      kkEnter: Exit(evAdvance);
    else
      Exit(evIgnore);
    end;
  end;

  if State = stFirmware then
  begin
    case Key.Kind of
      kkQuit: Exit(evQuit);
      kkUp: Exit(evSetUefi);
      kkDown: Exit(evSetBios);
      kkEnter: Exit(evAdvance);
      kkChar:
        begin
          if Key.Ch = '1' then
            Exit(evSetUefi);
          if Key.Ch = '2' then
            Exit(evSetBios);
          Exit(evIgnore);
        end;
    else
      Exit(evIgnore);
    end;
  end;

  Result := evIgnore;
end;

{ The state table as code. TargetMatches is consulted on exactly one edge:
  stConfirm + evAccept. }
function NextState(const State: TState; Event: TEvent;
  TargetMatches: Boolean): TState;
begin
  Result := State;
  case State of
    stNoDisks:
      Result := stLeave;
    stMismatch:
      Result := stLeave;
    stDiskChoice:
      case Event of
        evQuit: Result := stLeave;
        evAdvance: Result := stFirmware;
      end;
    stFirmware:
      case Event of
        evQuit: Result := stLeave;
        evAdvance: Result := stConfirm;
      end;
    stConfirm:
      case Event of
        evCancel: Result := stLeave;
        evAccept:
          if TargetMatches then
            Result := stPreviewing
          else
            Result := stMismatch;
      end;
    stPreviewing:
      case Event of
        evPreviewOk: Result := stDone;
        evPreviewFailed: Result := stPreviewError;
      end;
    stPreviewError:
      Result := stLeave;
    stDone:
      Result := stLeave;
    stLeave:
      Result := stLeave;
  end;
end;

{ The typed path against the chosen path. Deliberately a plain comparison with
  no trimming: guided.py strips, tui.py does not, and the TUI behaviour is what
  is being ported. The authoritative rule - including "must be a whole device"
  and "must not be the running system" - is wsmplan.ValidateTarget. }
function TargetMatches(const Typed, Path: string): Boolean;
begin
  Result := Typed = Path;
end;

{ ---- driver ----

  The same loop as run_tui, and the only code in this unit that can block: it
  calls Screen.ReadKey and Screen.Render and nothing else. Every decision above
  it is a pure function, so a scripted screen reproduces a whole session. }
function RunTui(const Screen: IScreen; const Disks: TCandidates;
  const Preview: TPreviewProc; const EvidenceNote: string): Integer;
var
  View: TView;
  Frame: TStringArray;
  Raw: string;
  Ev: TEvent;
  R: TPreviewResult;
  Matches: Boolean;
  Done: Boolean;
begin
  View.State := stDiskChoice;
  View.Disks := Disks;
  View.Selected := 0;
  View.Firmware := 'uefi';
  View.Typed := '';
  View.EvidenceNote := EvidenceNote;
  View.PreviewCode := 0;

  if Length(Disks) = 0 then
    View.State := stNoDisks;

  Result := 1;
  Done := False;
  while not Done do
  begin
    Frame := RenderView(View);
    if Length(Frame) > 0 then
      Screen.Render(Frame);

    case View.State of
      stNoDisks, stMismatch:
        begin
          Screen.ReadKey;
          View.State := NextState(View.State, evQuit, False);
        end;

      stPreviewing:
        begin
          R := Preview(View.Disks[View.Selected].Path,
            View.Disks[View.Selected].SizeBytes, View.Firmware);
          if R.HasCode and (R.Code <> 0) then
          begin
            View.PreviewCode := R.Code;
            Ev := evPreviewFailed;
          end
          else
            Ev := evPreviewOk;
          View.State := NextState(View.State, Ev, False);
        end;

      stDone:
        begin
          Result := 0;
          Done := True;
        end;

      stPreviewError:
        begin
          Result := View.PreviewCode;
          Done := True;
        end;

      stLeave:
        begin
          Result := 1;
          Done := True;
        end;

    else
      { stDiskChoice, stFirmware, stConfirm: one key, one transition. The list is
        never empty here - stNoDisks was taken above - so the modulo below is
        safe. }
      Raw := Screen.ReadKey;
      Ev := Transition(View.State, Raw);
      case Ev of
        evSelectUp:
          View.Selected := (View.Selected - 1 + Length(View.Disks)) mod
            Length(View.Disks);
        evSelectDown:
          View.Selected := (View.Selected + 1) mod Length(View.Disks);
        evSetUefi:
          View.Firmware := 'uefi';
        evSetBios:
          View.Firmware := 'bios';
        evAppend:
          View.Typed := View.Typed + Raw;
        evBackspace:
          if Length(View.Typed) > 0 then
            View.Typed := Utf8Copy(View.Typed, Utf8Length(View.Typed) - 1);
      end;
      if Ev = evAccept then
        Matches := TargetMatches(View.Typed, View.Disks[View.Selected].Path)
      else
        Matches := False;
      View.State := NextState(View.State, Ev, Matches);
    end;
  end;
end;

end.
