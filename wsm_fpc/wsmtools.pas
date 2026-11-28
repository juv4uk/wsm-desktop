unit wsmtools;

{ SPDX-License-Identifier: LicenseRef-Volnist }

{ Tool allowlist slice of the FPC port.

  Reproduces wsm_install.tool_map: one authoritative map from a logical tool name
  to its absolute executable and the Guix package that owns it.

  The Python module exists because of a divergence that had already happened: the
  planner listed seven tools including sgdisk, while the agent's allowlist listed
  six and did not, so the planner could emit a step the agent's own validator
  refused. Two lists, one truth, and the truth was whichever module you read.

  The port keeps the single source of truth: the table below is the only place a
  tool is added, and everything else derives from it.

  Not compiled here: no FPC in this environment. The self-check compares every
  entry against the Python map, so a divergence shows up on the first run. }

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

type
  TToolSpec = record
    Name: string;
    Executable: string;
    PackageName: string;
  end;

const
  TOOL_COUNT = 7;

  { Derived from wsm_install/tool_map.py. Adding a tool means adding one row here
    and nowhere else. }
  TOOLS: array[0..TOOL_COUNT - 1] of TToolSpec = (
    (Name: 'sgdisk';    Executable: '/usr/sbin/sgdisk';    PackageName: 'gptfdisk'),
    (Name: 'partprobe'; Executable: '/usr/sbin/partprobe'; PackageName: 'parted'),
    (Name: 'udevadm';   Executable: '/usr/bin/udevadm';    PackageName: 'eudev'),
    (Name: 'mkfs.ext4'; Executable: '/usr/sbin/mkfs.ext4'; PackageName: 'e2fsprogs'),
    (Name: 'mkfs.fat';  Executable: '/usr/sbin/mkfs.fat';  PackageName: 'dosfstools'),
    (Name: 'mount';     Executable: '/usr/bin/mount';      PackageName: 'util-linux'),
    (Name: 'mkdir';     Executable: '/usr/bin/mkdir';      PackageName: 'coreutils')
  );

function ToolIndex(const Name: string): Integer;
function ToolExecutable(const Name: string): string;
function ToolPackage(const Name: string): string;
function ToolNameFor(const Path: string): string;
function IsTrustedExecutable(const Path: string): Boolean;

implementation

{ -1 when the name is unknown, so callers must decide what an unknown tool means
  rather than receiving an empty string that looks like a valid path. }
function ToolIndex(const Name: string): Integer;
var
  I: Integer;
begin
  for I := 0 to TOOL_COUNT - 1 do
    if TOOLS[I].Name = Name then
      Exit(I);
  Result := -1;
end;

function ToolExecutable(const Name: string): string;
var
  I: Integer;
begin
  I := ToolIndex(Name);
  if I < 0 then
    raise Exception.Create('tool_map: unknown tool ' + Name);
  Result := TOOLS[I].Executable;
end;

function ToolPackage(const Name: string): string;
var
  I: Integer;
begin
  I := ToolIndex(Name);
  if I < 0 then
    raise Exception.Create('tool_map: unknown tool ' + Name);
  Result := TOOLS[I].PackageName;
end;

function ToolNameFor(const Path: string): string;
var
  I: Integer;
begin
  for I := 0 to TOOL_COUNT - 1 do
    if TOOLS[I].Executable = Path then
      Exit(TOOLS[I].Name);
  Result := '';
end;

{ The allowlist check the executor and the agent both need: an argv[0] is trusted
  only when it is one of these absolute paths. A basename is deliberately not
  enough - a bare "sgdisk" is what a PATH lookup would resolve, and that is the
  hole this table exists to close. }
function IsTrustedExecutable(const Path: string): Boolean;
var
  I: Integer;
begin
  for I := 0 to TOOL_COUNT - 1 do
    if TOOLS[I].Executable = Path then
      Exit(True);
  Result := False;
end;

end.
