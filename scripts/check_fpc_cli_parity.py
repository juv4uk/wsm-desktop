#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Differential harness: the Free Pascal front end against the Python CLI.

Two binaries answer the same question — "is this report usable, and may we
proceed" — and this script is the only place their answers are compared. It
runs both over a fixed table of reports and compares, for every case:

* the process exit code, exactly;
* the first line of stderr, after a documented normalisation.

Why stderr and not stdout: the two front ends deliberately do not emit the same
stdout. The Python CLI prints the draft plan document (``wsm_install.plan``),
which the Pascal front end does not implement. What must never differ is the
*decision*: the exit code, and the first thing said about why.

The normalisation is narrow on purpose. Only the text a JSON decoder or the
argparse help-wrapping produces is dropped, because those are library artefacts
of the implementation language and not part of the contract. Every other line
must match byte for byte. If a case needs a new normalisation, add it to
``NORMALISERS`` with the reason — do not widen an existing one.

Usage::

    # both binaries (what CI runs, after Guix has built the Pascal one)
    python3 scripts/check_fpc_cli_parity.py \
        --python "python3 -m wsm_install" \
        --pascal /gnu/store/.../bin/wsm-install-fpc

    # only the Python side: re-records the documented contract
    python3 scripts/check_fpc_cli_parity.py --python-only

    # the harness' own behaviour, with mocked binaries; needs no FPC
    python3 scripts/check_fpc_cli_parity.py --self-test

Exit status: 0 when every case agrees, 1 otherwise. A missing binary is a
failure, not a skip: a harness that passes because it could not run proves
nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hardware"
BASE_REPORT = FIXTURES / "complete-machine.json"

# The two read-only front-end modes the Pascal binary implements.
PREFLIGHT = "preflight"
CLASSIFY = "classify"
MODES = (PREFLIGHT, CLASSIFY)

# Exit codes, from wsm_install/cli.py. Named so the table below reads as a
# contract rather than as bare integers.
EXIT_OK = 0
EXIT_REFUSED = 2  # argparse refusal, unreadable/invalid report, schema refusal
EXIT_BLOCKED = 3  # report is valid, required critical evidence is unresolved


@dataclass(frozen=True)
class Case:
    """One report, and what both binaries must say about it.

    ``expect_exit``/``expect_stderr`` are what the *Python* CLI is recorded as
    doing. Asserting them here means a change in the Python contract shows up
    as a harness failure instead of silently redefining parity.
    """

    name: str
    mutate: Callable[[dict], None] | None
    expect_exit: int
    expect_stderr: str
    #: True when the Pascal front end is allowed to be *stricter* than Python
    #: (refuse where Python accepts) and the difference is deliberate.
    allow_stricter_pascal: bool = False
    #: Set for cases whose report is not a JSON document at all.
    raw_text: str | None = None
    #: Read from a fixture instead of ``BASE_REPORT``.
    source: Path | None = None

    def expectations(self, mode: str) -> tuple[int, str]:
        """Recorded Python behaviour for one mode.

        ``--classify`` prints its summary to stdout and nothing to stderr, and
        a report that blocks a *plan* still classifies: the classification is
        diagnostic and decides no install readiness. So the plan blocker that
        makes ``--preflight`` exit 3 does not change ``--classify``.
        """
        if mode == CLASSIFY:
            if self.expect_exit in (EXIT_OK, EXIT_BLOCKED):
                # Accepted: the summary goes to stdout, stderr stays empty.
                return (EXIT_OK, "")
            # Refused before the mode is dispatched: same refusal, same line.
            return (self.expect_exit, self.expect_stderr)
        return (self.expect_exit, self.expect_stderr)


def _drop(name: str) -> Callable[[dict], None]:
    return lambda report: report.pop(name, None)


def _set(key: str, value: object) -> Callable[[dict], None]:
    def apply(report: dict) -> None:
        report[key] = value

    return apply


def _set_nested(path: Sequence[str], value: object) -> Callable[[dict], None]:
    def apply(report: dict) -> None:
        target = report
        for step in path[:-1]:
            target = target[step]
        target[path[-1]] = value

    return apply


def _break_gpu_device_id(report: dict) -> None:
    for device in report["devices"]:
        if device.get("category") == "gpu":
            device.setdefault("identity", {})["vendor_id"] = "0x10de"
            device["identity"]["device_id"] = "zzzz"
            return
    raise AssertionError("the base fixture has no gpu device to break")


def _half_gpu_identity_pair(report: dict) -> None:
    for device in report["devices"]:
        if device.get("category") == "gpu":
            device["identity"] = {"vendor_id": "0x10de"}
            return
    raise AssertionError("the base fixture has no gpu device to break")


def _bad_boot_mode(report: dict) -> None:
    report["environment"]["boot_mode"] = "coreboot"


#: The table. Every case is run in both modes.
CASES: tuple[Case, ...] = (
    Case(
        "valid-1.0.0",
        None,
        EXIT_OK,
        "WSM hardware preflight — report fixture-complete-machine-20261126",
    ),
    Case(
        "valid-1.1.0",
        _set("schema_version", "1.1.0"),
        EXIT_OK,
        "WSM hardware preflight — report fixture-complete-machine-20261126",
    ),
    Case(
        "missing-required-field",
        _drop("report_id"),
        EXIT_REFUSED,
        "wsm-install: schema error at $: 'report_id' is a required property",
    ),
    Case(
        "missing-environment",
        _drop("environment"),
        EXIT_REFUSED,
        "wsm-install: schema error at $: 'environment' is a required property",
    ),
    Case(
        "unsupported-version",
        _set("schema_version", "9.0.0"),
        EXIT_REFUSED,
        "wsm-install: unsupported hardware report schema '9.0.0'; supported: 1.0.0, 1.1.0",
    ),
    Case(
        "missing-schema-version",
        _drop("schema_version"),
        EXIT_REFUSED,
        "wsm-install: unsupported hardware report schema None; supported: 1.0.0, 1.1.0",
    ),
    Case(
        "wrong-gpu-identity",
        _break_gpu_device_id,
        EXIT_REFUSED,
        "wsm-install: schema error at devices.6.identity.device_id: "
        "'zzzz' does not match '^(0x)?[0-9a-fA-F]{4}$'",
    ),
    Case(
        # JSON Schema cannot express "both or neither", so the Python CLI
        # accepts this report. The Pascal front end refuses it: a GPU that
        # names one half of its identity has an identity nobody can check, and
        # docs/INSTALLER-PREFLIGHT.md forbids proceeding on an unexplained
        # unknown. The delta is one-directional (refuse more, never less).
        "half-gpu-identity-pair",
        _half_gpu_identity_pair,
        EXIT_OK,
        "WSM hardware preflight — report fixture-complete-machine-20261126",
        allow_stricter_pascal=True,
    ),
    Case(
        "invalid-boot-mode",
        _bad_boot_mode,
        EXIT_REFUSED,
        "wsm-install: schema error at environment.boot_mode: "
        "'coreboot' is not one of ['uefi', 'bios', 'unknown']",
    ),
    Case(
        "malformed-json",
        None,
        EXIT_REFUSED,
        "wsm-install: invalid report JSON: Expecting property name enclosed in "
        "double quotes: line 1 column 2 (char 1)",
        raw_text="{broken",
    ),
    Case(
        "blocked-critical-evidence",
        None,
        EXIT_BLOCKED,
        "WSM hardware preflight — report example-unknown-20261125-c3",
        source=FIXTURES / "unknown-incomplete.json",
    ),
)


#: ``(pattern, replacement)`` pairs applied to a stderr first line before
#: comparison. Each one drops text that belongs to the implementation language,
#: not to the contract.
NORMALISERS: tuple[tuple[re.Pattern[str], str], ...] = (
    # json.JSONDecodeError carries a message and a character offset; a Pascal
    # decoder cannot produce the same wording, and the decision is the prefix.
    (
        re.compile(r"^wsm-install: invalid report JSON: .*$"),
        "wsm-install: invalid report JSON",
    ),
    # OSError text is the host's errno wording.
    (re.compile(r"^wsm-install: cannot read report: .*$"), "wsm-install: cannot read report"),
    # argparse wraps `usage:` and `wsm-install: error:` to the terminal width.
    (re.compile(r"^usage: .*$"), "usage: wsm-install"),
    (re.compile(r"^wsm-install: error: .*$"), "wsm-install: error"),
)


def normalise_stderr_line(line: str) -> str:
    """Drop implementation-language text from a stderr first line."""
    for pattern, replacement in NORMALISERS:
        if pattern.match(line):
            return replacement
    return line


def first_stderr_line(stderr: str) -> str:
    lines = stderr.splitlines()
    return lines[0] if lines else ""


@dataclass
class Observation:
    """What one binary did with one case."""

    exit_code: int | None
    stderr_first: str
    stdout: str = ""
    error: str = ""


@dataclass
class Verdict:
    case: str
    mode: str
    ok: bool
    detail: str
    python: Observation | None = None
    pascal: Observation | None = None
    documented_strictness: bool = False


@dataclass
class Summary:
    verdicts: list[Verdict] = field(default_factory=list)

    def failures(self) -> list[Verdict]:
        return [verdict for verdict in self.verdicts if not verdict.ok]

    @property
    def ok(self) -> bool:
        return not self.failures()


def build_reports(directory: Path) -> dict[str, Path]:
    """Materialise the case table as files under ``directory``."""
    base_text = BASE_REPORT.read_text(encoding="utf-8")
    written: dict[str, Path] = {}
    for case in CASES:
        destination = directory / f"{case.name}.json"
        if case.raw_text is not None:
            destination.write_text(case.raw_text, encoding="utf-8")
        elif case.source is not None:
            destination.write_text(case.source.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            report = json.loads(base_text)
            if case.mutate is not None:
                case.mutate(report)
            destination.write_text(json.dumps(report), encoding="utf-8")
        written[case.name] = destination
    return written


def command_for(binary: Sequence[str], report: Path, mode: str) -> list[str]:
    """The exact argv both binaries are given for one case."""
    argv = [*binary, "--preflight", "--report", str(report), "--backend", "guix", "--dry-run"]
    if mode == CLASSIFY:
        argv.append("--classify")
    return argv


def run_once(argv: Sequence[str], timeout: float = 120.0) -> Observation:
    try:
        completed = subprocess.run(
            list(argv), capture_output=True, text=True, check=False, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Observation(exit_code=None, stderr_first="", error=f"cannot run {argv[0]}: {exc}")
    return Observation(
        exit_code=completed.returncode,
        stderr_first=first_stderr_line(completed.stderr),
        stdout=completed.stdout,
    )


def judge(
    case: Case,
    mode: str,
    python: Observation,
    pascal: Observation,
) -> Verdict:
    """Compare two observations for one case. Pure: no subprocess, no I/O."""
    if python.exit_code is None:
        return Verdict(case.name, mode, False, f"python side did not run: {python.error}", python, pascal)
    if pascal.exit_code is None:
        return Verdict(case.name, mode, False, f"pascal side did not run: {pascal.error}", python, pascal)

    problems: list[str] = []
    strictness: list[str] = []

    expected_exit, expected_stderr = case.expectations(mode)
    if python.exit_code != expected_exit:
        problems.append(
            f"python contract drift: exit {python.exit_code}, documented {expected_exit}"
        )
    if normalise_stderr_line(python.stderr_first) != normalise_stderr_line(expected_stderr):
        problems.append(
            f"python contract drift: stderr {python.stderr_first!r}, documented {expected_stderr!r}"
        )

    # Refusing more than Python is the one permitted direction, and only for a
    # case that says so. Accepting what Python refuses is never permitted.
    stricter = pascal.exit_code > python.exit_code
    allowed_strictness = stricter and case.allow_stricter_pascal
    if pascal.exit_code != python.exit_code and not allowed_strictness:
        problems.append(f"exit codes differ: python {python.exit_code}, pascal {pascal.exit_code}")

    python_line = normalise_stderr_line(python.stderr_first)
    pascal_line = normalise_stderr_line(pascal.stderr_first)
    if python_line != pascal_line:
        if allowed_strictness:
            strictness.append("pascal refuses where python accepts (documented)")
        else:
            problems.append(f"stderr differs: python {python_line!r}, pascal {pascal_line!r}")

    if problems:
        return Verdict(case.name, mode, False, "; ".join(problems), python, pascal)
    detail = "; ".join(strictness) if strictness else "agree"
    return Verdict(case.name, mode, True, detail, python, pascal, bool(strictness))


def check_binary(argv: Sequence[str]) -> str | None:
    """Return an error string when ``argv`` cannot even answer ``--version``."""
    observation = run_once([*argv, "--version"], timeout=60.0)
    if observation.exit_code is None:
        return observation.error
    if observation.exit_code != 0:
        return f"{' '.join(argv)} --version exited {observation.exit_code}"
    return None


def run_table(
    python_binary: Sequence[str],
    pascal_binary: Sequence[str] | None,
) -> Summary:
    summary = Summary()
    with tempfile.TemporaryDirectory() as temporary:
        reports = build_reports(Path(temporary))
        for case in CASES:
            for mode in MODES:
                python = run_once(command_for(python_binary, reports[case.name], mode))
                if pascal_binary is None:
                    expected_exit, expected_stderr = case.expectations(mode)
                    ok = python.exit_code == expected_exit and (
                        normalise_stderr_line(python.stderr_first)
                        == normalise_stderr_line(expected_stderr)
                    )
                    detail = "python contract holds" if ok else "python contract drift"
                    summary.verdicts.append(
                        Verdict(case.name, mode, ok, detail, python, None)
                    )
                    continue
                pascal = run_once(command_for(pascal_binary, reports[case.name], mode))
                summary.verdicts.append(judge(case, mode, python, pascal))
    return summary


def render(summary: Summary) -> str:
    lines = [
        f"{'case':30s} {'mode':10s} {'result':8s} detail",
        "-" * 100,
    ]
    for verdict in summary.verdicts:
        state = "ok" if verdict.ok else "FAIL"
        lines.append(f"{verdict.case:30s} {verdict.mode:10s} {state:8s} {verdict.detail}")
    failures = summary.failures()
    lines.append("-" * 100)
    lines.append(
        f"{len(summary.verdicts)} comparisons, {len(failures)} failed"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test: proves the harness detects divergence, without needing FPC.
# ---------------------------------------------------------------------------

FAKE_BINARY = '''#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Stand-in for one front end. Reads a table; never decides anything itself."""
import json
import os
import sys

table = json.loads(open(os.environ["FAKE_TABLE"], encoding="utf-8").read())
report = "?"
mode = "classify" if "--classify" in sys.argv[1:] else "preflight"
for index, argument in enumerate(sys.argv[1:]):
    if argument == "--report":
        report = os.path.basename(sys.argv[index + 2])
record = table.get(f"{report}|{mode}", table.get(f"{report}|preflight", [0, ""]))
sys.stderr.write((record[1] + "\\n") if record[1] else "")
sys.exit(record[0])
'''


def _write_fake(directory: Path, name: str, table: dict) -> tuple[Path, Path]:
    script = directory / f"{name}.py"
    script.write_text(FAKE_BINARY, encoding="utf-8")
    script.chmod(0o755)
    table_path = directory / f"{name}-table.json"
    table_path.write_text(json.dumps(table), encoding="utf-8")
    return script, table_path


def _table_from_cases(overrides: dict[str, list] | None = None) -> dict:
    table: dict[str, list] = {}
    for case in CASES:
        for mode in MODES:
            key = f"{case.name}.json|{mode}"
            expected_exit, expected_stderr = case.expectations(mode)
            table[key] = [expected_exit, expected_stderr]
    if overrides:
        table.update(overrides)
    return table


def self_test() -> int:
    """Run the harness against mocked binaries and require it to notice lies."""
    problems: list[str] = []

    def expect(label: str, condition: bool, detail: str = "") -> None:
        if not condition:
            problems.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        base = _table_from_cases()

        python_script, python_table = _write_fake(directory, "python", base)
        pascal_script, pascal_table = _write_fake(directory, "pascal", base)

        python_binary = [sys.executable, str(python_script)]
        pascal_binary = [sys.executable, str(pascal_script)]

        def run(python_env: Path, pascal_env: Path) -> Summary:
            """Compare two mocked front ends, each reading its own table.

            The table is passed through the environment, so it is set
            immediately before each subprocess call.
            """
            summary = Summary()
            previous = os.environ.get("FAKE_TABLE")
            try:
                with tempfile.TemporaryDirectory() as reports_dir:
                    reports = build_reports(Path(reports_dir))
                    for case in CASES:
                        for mode in MODES:
                            argv = command_for(python_binary, reports[case.name], mode)
                            os.environ["FAKE_TABLE"] = str(python_env)
                            python = run_once(argv)
                            os.environ["FAKE_TABLE"] = str(pascal_env)
                            pascal = run_once(argv)
                            summary.verdicts.append(judge(case, mode, python, pascal))
            finally:
                if previous is None:
                    os.environ.pop("FAKE_TABLE", None)
                else:
                    os.environ["FAKE_TABLE"] = previous
            return summary

        agreeing = run(python_table, pascal_table)
        expect(
            "mocked binaries that agree must pass",
            agreeing.ok,
            render(agreeing),
        )
        expect(
            "an agreeing run must still compare every case",
            len(agreeing.verdicts) == len(CASES) * len(MODES),
            f"{len(agreeing.verdicts)} comparisons",
        )

        # 1. A different exit code must be caught.
        diverging = _table_from_cases({"missing-required-field.json|preflight": [EXIT_OK, ""]})
        _, divergent_table = _write_fake(directory, "divergent", diverging)
        caught = run(python_table, divergent_table)
        expect("a differing exit code must fail", not caught.ok, "the harness called it parity")
        expect(
            "the differing case must be named",
            any(verdict.case == "missing-required-field" for verdict in caught.failures()),
            render(caught),
        )

        # 2. A different first stderr line at the same exit code must be caught.
        reworded = _table_from_cases(
            {"unsupported-version.json|preflight": [EXIT_REFUSED, "wsm-install: nope"]}
        )
        _, reworded_table = _write_fake(directory, "reworded", reworded)
        caught = run(python_table, reworded_table)
        expect("a differing stderr first line must fail", not caught.ok, "the harness called it parity")
        expect(
            "the reworded case must be named",
            any(verdict.case == "unsupported-version" for verdict in caught.failures()),
            render(caught),
        )

        # 3. A dropped stderr line must be caught too.
        silent = _table_from_cases({"valid-1.0.0.json|preflight": [EXIT_OK, ""]})
        _, silent_table = _write_fake(directory, "silent", silent)
        caught = run(python_table, silent_table)
        expect("a missing stderr first line must fail", not caught.ok, "the harness called it parity")

        # 4. A documented strictness must not be a failure...
        stricter = _table_from_cases(
            {"half-gpu-identity-pair.json|preflight": [EXIT_REFUSED, "wsm-install: stricter"]}
        )
        _, stricter_table = _write_fake(directory, "stricter", stricter)
        allowed = run(python_table, stricter_table)
        expect("documented strictness must pass", allowed.ok, render(allowed))
        expect(
            "documented strictness must be reported, not hidden",
            any(verdict.documented_strictness for verdict in allowed.verdicts),
            render(allowed),
        )

        # 5. ...but the reverse direction never is: pascal accepting what
        #    python refuses would be a fail-open regression.
        lenient = _table_from_cases(
            {"missing-required-field.json|preflight": [EXIT_OK, "WSM hardware preflight — report x"]}
        )
        _, lenient_table = _write_fake(directory, "lenient", lenient)
        caught = run(python_table, lenient_table)
        expect("pascal accepting what python refuses must fail", not caught.ok, render(caught))

        # 6. A binary that cannot run at all must be a failure, not a skip.
        missing = run_once([str(directory / "does-not-exist")])
        expect("a missing binary must not look like agreement", missing.exit_code is None)

    if problems:
        print("self-test failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        "self-test passed: the harness detects exit-code, stderr, silence, "
        "strictness and fail-open divergence against mocked binaries."
    )
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", default="python3 -m wsm_install",
                        help="command for the Python CLI (default: python3 -m wsm_install)")
    parser.add_argument("--pascal", help="path to the compiled wsm-install-fpc binary")
    parser.add_argument("--python-only", action="store_true",
                        help="record and check only the Python side of the contract")
    parser.add_argument("--self-test", action="store_true",
                        help="test this harness against mocked binaries; needs no FPC")
    arguments = parser.parse_args(list(argv) if argv is not None else None)

    if arguments.self_test:
        return self_test()

    python_binary = shlex.split(arguments.python)
    problem = check_binary(python_binary)
    if problem:
        print(f"check-fpc-cli-parity: {problem}", file=sys.stderr)
        return 1

    if arguments.python_only:
        summary = run_table(python_binary, None)
        print(render(summary))
        return 0 if summary.ok else 1

    if not arguments.pascal:
        print(
            "check-fpc-cli-parity: --pascal is required unless --python-only or "
            "--self-test is given; a parity check with one side is not a parity check",
            file=sys.stderr,
        )
        return 1

    pascal_binary = [arguments.pascal]
    problem = check_binary(pascal_binary)
    if problem:
        print(f"check-fpc-cli-parity: {problem}", file=sys.stderr)
        return 1

    summary = run_table(python_binary, pascal_binary)
    print(render(summary))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
