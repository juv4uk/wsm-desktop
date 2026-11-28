# SPDX-License-Identifier: LicenseRef-Volnist
"""Prove, from inside a running system, that the installer's tools are there.

#645's last acceptance item asks for more than a build: every allowlisted
executable path must exist *and* be executable in the live system that actually
boots. `scripts/check_tool_closure.py` answers that question for a directory it
is pointed at, which is all a host can do — a directory is not a running system,
and existence in the build environment proves nothing about the image.

This module is the piece that runs *in* the guest and the piece that reads what
it said, so the protocol has exactly one definition:

* :func:`inspect` runs in the guest, resolves each tool by the same rule the
  planner uses (`wsm_install.tools.resolve` over an explicit prefix list, never
  `PATH`), and returns a state per tool;
* :func:`render` turns those states into the machine-readable lines the guest
  prints on the serial console;
* :func:`parse` runs on the host over the captured serial text and returns a
  verdict, so the boot harness can put a pass or a fail in its evidence instead
  of an observation a reader has to interpret.

The line format is deliberately boring: one line per tool, `|`-separated, ASCII
only, versioned. It survives a serial console and it can be read with `grep`.

    WSM_TOOL_CLOSURE|v1|<name>|<path>|<state>
    WSM_TOOL_CLOSURE_SUMMARY|v1|<ok|fail>|<usable>/<total>

`state` is one of :data:`STATES`. `-` stands for "no path": a tool that could
not be resolved in any prefix has nowhere to point at.

Read-only by construction: :func:`inspect` calls `stat` and `access` and nothing
else. It does not execute the tools it checks, does not mount anything, does not
open a block device and does not write to any disk. The guest proves the tools
exist; it never uses them.

A failure is never silent. An empty report is a failure, not a pass: when the
harness is asked for a verdict and the guest printed no lines at all, every tool
is missing and the verdict says so. The one "we did not check" value,
``not-checked``, exists only in the harness and only when the caller did not ask
for the check.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from wsm_install.tool_map import TOOLS, package
from wsm_install.tools import DEFAULT_PREFIXES, resolve

PROTOCOL_VERSION = "v1"
LINE_PREFIX = "WSM_TOOL_CLOSURE"
SUMMARY_PREFIX = "WSM_TOOL_CLOSURE_SUMMARY"
FIELD_SEPARATOR = "|"
NO_PATH = "-"

STATE_OK = "ok"
STATE_MISSING = "missing"
STATE_NOT_FILE = "not-file"
STATE_NOT_EXECUTABLE = "not-executable"
STATE_UNRESOLVED = "unresolved"
STATES: tuple[str, ...] = (
    STATE_OK,
    STATE_MISSING,
    STATE_NOT_FILE,
    STATE_NOT_EXECUTABLE,
    STATE_UNRESOLVED,
)

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_NOT_CHECKED = "not-checked"


@dataclass(frozen=True)
class ToolState:
    """What one tool looked like from inside the guest."""

    name: str
    path: str
    state: str
    detail: str | None = None


@dataclass(frozen=True)
class Verdict:
    """The host-side reading of what the guest printed."""

    status: str
    expected: tuple[str, ...]
    reported: dict[str, dict[str, str]]
    missing: tuple[str, ...]
    not_executable: tuple[str, ...]
    problems: tuple[str, ...]
    summary: str | None
    reported_lines: int

    def as_dict(self) -> dict[str, Any]:
        """The evidence-JSON shape; every field is a claim this run supports."""
        return {
            "status": self.status,
            "protocol": PROTOCOL_VERSION,
            "expected": list(self.expected),
            "reported": {name: dict(fields) for name, fields in self.reported.items()},
            "missing": list(self.missing),
            "not_executable": list(self.not_executable),
            "problems": list(self.problems),
            "summary": self.summary,
            "reported_lines": self.reported_lines,
        }


def tool_state(name: str, root: Path | str, path: str) -> tuple[str, str | None]:
    """Classify `path` under `root` for the tool `name`.

    The messages are the ones `scripts/check_tool_closure.py` prints, because
    the fix for a failure is "add that package to the image closure", not
    "create that file" — so the owning package has to be named.
    """
    owner = package(name)
    candidate = Path(root) / path.lstrip("/")
    if not candidate.exists():
        return STATE_MISSING, (
            f"{path} does not exist under {root} (owned by package {owner})"
        )
    if not candidate.is_file():
        return STATE_NOT_FILE, (
            f"{path} is not a regular file under {root} (owned by package {owner})"
        )
    if not os.access(candidate, os.X_OK):
        return STATE_NOT_EXECUTABLE, (
            f"{path} is not executable under {root} (owned by package {owner})"
        )
    return STATE_OK, None


def tool_problem(name: str, root: Path | str, path: str) -> str | None:
    """Why `path` is not usable under `root`, or None when it is."""
    return tool_state(name, root, path)[1]


def inspect(
    root: Path | str = "/",
    prefixes: Sequence[str] | None = None,
) -> list[ToolState]:
    """Read-only state of every trusted tool as seen from inside `root`.

    `prefixes` is the image's own profile directories (a Guix image has no
    `/usr`); without it the FHS paths in the tool table are used. Resolution
    goes through :func:`wsm_install.tools.resolve`, so this reports the same
    path the planner would choose.
    """
    root = Path(root)
    selected = tuple(prefixes) if prefixes else DEFAULT_PREFIXES
    states: list[ToolState] = []
    for name in sorted(TOOLS):
        expected = resolve(
            name,
            prefixes=selected,
            exists=lambda candidate: (root / candidate.lstrip("/")).exists(),
        )
        if expected is None:
            states.append(
                ToolState(
                    name,
                    "",
                    STATE_UNRESOLVED,
                    f"not found in any of {list(selected)} under {root}",
                )
            )
            continue
        state, detail = tool_state(name, root, expected)
        states.append(ToolState(name, expected, state, detail))
    return states


def render(states: Sequence[ToolState]) -> list[str]:
    """The protocol lines for `states`, summary last."""
    lines = [
        FIELD_SEPARATOR.join(
            (LINE_PREFIX, PROTOCOL_VERSION, state.name, state.path or NO_PATH, state.state)
        )
        for state in states
    ]
    usable = sum(1 for state in states if state.state == STATE_OK)
    verdict = "ok" if states and usable == len(states) else "fail"
    lines.append(
        FIELD_SEPARATOR.join(
            (SUMMARY_PREFIX, PROTOCOL_VERSION, verdict, f"{usable}/{len(states)}")
        )
    )
    return lines


def parse(serial_text: str, expected: Sequence[str] | None = None) -> Verdict:
    """Read the guest's answer out of captured serial text.

    A v1 report is complete only when every expected tool row and exactly one
    internally consistent summary line are present. Silence or a partial summary
    is never a pass.
    """
    names = tuple(sorted(expected if expected is not None else TOOLS))
    reported: dict[str, dict[str, str]] = {}
    problems: list[str] = []
    row_protocol_error = False
    summary_count = 0
    parsed_summary: tuple[str, int, int] | None = None

    for raw in serial_text.splitlines():
        line = raw.strip()
        if not line.startswith(LINE_PREFIX):
            continue
        if line.startswith(SUMMARY_PREFIX):
            summary_count += 1
            if summary_count > 1:
                problems.append("summary line was reported more than once")
                continue
            fields = line.split(FIELD_SEPARATOR)
            counts = re.fullmatch(r"(0|[1-9][0-9]*)/(0|[1-9][0-9]*)", fields[3]) if len(fields) == 4 else None
            if (
                len(fields) != 4
                or fields[1] != PROTOCOL_VERSION
                or fields[2] not in {"ok", "fail"}
                or counts is None
            ):
                problems.append(f"malformed summary line: {line!r}")
                continue
            parsed_summary = (fields[2], int(counts.group(1)), int(counts.group(2)))
            continue
        fields = line.split(FIELD_SEPARATOR)
        if len(fields) != 5 or fields[1] != PROTOCOL_VERSION:
            problems.append(f"malformed probe line: {line!r}")
            row_protocol_error = True
            continue
        name, path, state = fields[2], fields[3], fields[4]
        if state not in STATES:
            problems.append(f"{name}: unknown state {state!r}")
            row_protocol_error = True
            continue
        if name in reported:
            problems.append(f"{name} was reported more than once")
            row_protocol_error = True
            continue
        if name not in names:
            problems.append(f"{name} is not one of the expected tools")
            row_protocol_error = True
            continue
        reported[name] = {"path": "" if path == NO_PATH else path, "state": state}

    if summary_count == 0:
        problems.append("required summary line was not reported by the guest")
    elif parsed_summary is None:
        problems.append("summary line was not valid")

    absent = tuple(name for name in names if name not in reported)
    for name in absent:
        problems.append(f"{name} was not reported by the guest")
    # A tool the guest resolved nowhere is as missing as one it never mentioned.
    unresolved = tuple(
        name for name, fields in reported.items() if fields["state"] == STATE_UNRESOLVED
    )
    missing = tuple(sorted(set(absent) | set(unresolved)))
    not_executable = tuple(
        name for name, fields in reported.items() if fields["state"] == STATE_NOT_EXECUTABLE
    )
    for name, fields in sorted(reported.items()):
        if fields["state"] == STATE_OK:
            continue
        if fields["state"] == STATE_NOT_EXECUTABLE:
            problems.append(f"{name}: not executable at {fields['path'] or 'no path'}")
            continue
        problems.append(f"{name}: {fields['state']} at {fields['path'] or 'no path'}")

    usable = sum(1 for fields in reported.values() if fields["state"] == STATE_OK)
    expected_verdict = (
        "ok"
        if not row_protocol_error and not absent and usable == len(names)
        else "fail"
    )
    summary_text: str | None = None
    if parsed_summary is not None:
        summary_verdict, summary_usable, summary_total = parsed_summary
        summary_text = f"{summary_verdict} {summary_usable}/{summary_total}"
        if summary_total != len(names):
            problems.append(
                f"summary total {summary_total} does not match expected tool count {len(names)}"
            )
        if summary_usable != usable:
            problems.append(
                f"summary usable count {summary_usable} does not match reported ok rows {usable}"
            )
        if summary_verdict != expected_verdict:
            problems.append(
                f"summary verdict {summary_verdict!r} does not match tool rows ({expected_verdict!r})"
            )

    return Verdict(
        status=STATUS_PASS if not problems else STATUS_FAIL,
        expected=names,
        reported=reported,
        missing=missing,
        not_executable=not_executable,
        problems=tuple(problems),
        summary=summary_text,
        reported_lines=len(reported),
    )


def not_checked(marker: str | None = None) -> dict[str, Any]:
    """The evidence value for "this run did not ask the guest"."""
    return {
        "status": STATUS_NOT_CHECKED,
        "protocol": PROTOCOL_VERSION,
        "marker": marker,
        "expected": sorted(TOOLS),
        "reported": {},
        "missing": [],
        "not_executable": [],
        "problems": [],
        "summary": None,
        "reported_lines": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m wsm_install.tool_closure",
        description=(
            "Report whether the installer's tools exist in this system and are "
            "executable. Read-only: stat and access, nothing else."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/"),
        help="tree to inspect; the default is the running system",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=None,
        metavar="DIR",
        help=(
            "resolve each tool inside DIR under --root instead of using the FHS "
            "path in the table; repeatable, first hit wins"
        ),
    )
    parser.add_argument(
        "--console",
        metavar="PATH",
        help="append the report to PATH (for example /dev/console) instead of stdout",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    states = inspect(args.root, args.prefix)
    text = "\n".join(render(states)) + "\n"
    if args.console:
        try:
            with open(args.console, "a", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
        except OSError as exc:
            print(f"tool-closure: cannot write to {args.console}: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(text)
        sys.stdout.flush()
    return 0 if all(state.state == STATE_OK for state in states) else 1


if __name__ == "__main__":
    raise SystemExit(main())
