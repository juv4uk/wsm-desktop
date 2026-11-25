# SPDX-License-Identifier: LicenseRef-Volnist
"""Build one conservative release verdict from the checks that actually ran.

A check that did not run is never promoted to pass. The nested ISO verifier has
its own versioned verdict, which must be parsed rather than inferred from its
process exit code.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "wsm-release-gate/1"
VERSION = "0.1.1"
ROOT = Path(__file__).resolve().parents[1]
IMAGE_VERDICT_SCHEMA = "wsm-release-verdict/1"
IMAGE_CRITERIA = {"checksum", "manifest", "iso-structure", "boot-bios", "boot-uefi"}


def run(command: list[str], timeout: int = 900) -> tuple[int, str]:
    """Run a read-only check and return (returncode, last meaningful line)."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, f"could not complete {command[0]}: {exc}"
    output = (completed.stdout + completed.stderr).strip().splitlines()
    tail = output[-1] if output else "no output"
    return completed.returncode, tail[:300]


def criterion(identifier: str, status: str, detail: str) -> dict[str, str]:
    return {"id": identifier, "status": status, "detail": detail}


def from_exit(identifier: str, code: int, detail: str) -> dict[str, str]:
    if code == -1:
        return criterion(identifier, "not-run", detail)
    return criterion(identifier, "pass" if code == 0 else "fail", detail)


def check_docs() -> dict[str, str]:
    code, detail = run([sys.executable, "scripts/check_docs.py"])
    return from_exit("docs", code, detail)


def check_channels() -> dict[str, str]:
    """Check each product against its own lock; absence is not a PASS."""
    results: list[dict[str, str]] = []
    policies = (
        ("free", ROOT / "channels.lock.scm"),
        ("compatibility", ROOT / "channels.compatibility.lock.scm"),
    )
    for policy, lock in policies:
        if not lock.is_file():
            results.append(
                criterion(
                    f"channels-{policy}",
                    "not-run",
                    f"{lock.name} NOT_CONFIGURED; no fallback to another product lock",
                )
            )
            continue
        code, detail = run(
            [
                sys.executable,
                "scripts/check_channels.py",
                "--policy",
                policy,
                "--lock",
                str(lock),
            ]
        )
        results.append(from_exit(f"channels-{policy}", code, detail))

    failures = [item for item in results if item["status"] == "fail"]
    if failures:
        details = "; ".join(f'{item["id"]}: {item["detail"]}' for item in failures)
        return criterion("channels", "fail", details[:300])
    not_run = [item for item in results if item["status"] == "not-run"]
    if not_run:
        details = "; ".join(f'{item["id"]}: {item["detail"]}' for item in not_run)
        return criterion("channels", "not-run", details[:300])
    return criterion("channels", "pass", "separate Free and Compatibility locks satisfy their policies")


def check_tests() -> dict[str, str]:
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    if not tests:
        return criterion("tests", "not-run", "no test files found")
    failures: list[str] = []
    for path in tests:
        code, detail = run([sys.executable, str(path)])
        if code != 0:
            failures.append(f"{path.name}: {detail}")
    if failures:
        return criterion("tests", "fail", "; ".join(failures)[:300])
    return criterion("tests", "pass", f"{len(tests)} test files green")


def check_evidence() -> dict[str, str]:
    code, detail = run([sys.executable, "scripts/check_profile_evidence.py"])
    if code == 0 and (
        "no evidence bundles yet" in detail
        or "no profiles directory at" in detail
    ):
        return criterion("profile-evidence", "not-run", detail)
    return from_exit("profile-evidence", code, detail)


def _image_verdict_problem(payload: Any, iso: Path) -> str | None:
    """Validate the nested verifier contract and recompute its aggregate state."""
    if not isinstance(payload, dict):
        return "nested image verdict root is not an object"
    if payload.get("schema") != IMAGE_VERDICT_SCHEMA:
        return "nested image verdict has an unsupported schema"
    if payload.get("artifact") != iso.name:
        return "nested image verdict names a different artifact"

    criteria = payload.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return "nested image verdict has no criteria"
    indexed: dict[str, dict[str, Any]] = {}
    for item in criteria:
        if not isinstance(item, dict):
            return "nested image verdict contains a malformed criterion"
        identifier = item.get("id")
        status = item.get("status")
        if not isinstance(identifier, str) or identifier in indexed:
            return "nested image verdict contains a missing or duplicate criterion id"
        if not isinstance(status, str) or status not in {"pass", "fail", "not-run"}:
            return f"nested image verdict has an invalid status for {identifier!r}"
        if not isinstance(item.get("detail"), str):
            return f"nested image verdict has no detail for {identifier!r}"
        indexed[identifier] = item

    if set(indexed) != IMAGE_CRITERIA:
        missing = sorted(IMAGE_CRITERIA - indexed.keys())
        extra = sorted(indexed.keys() - IMAGE_CRITERIA)
        return f"nested image criteria mismatch (missing={missing}, extra={extra})"

    statuses = {item["status"] for item in indexed.values()}
    expected = "fail" if "fail" in statuses else "incomplete" if "not-run" in statuses else "pass"
    if payload.get("overall") != expected:
        return "nested image verdict overall does not match its criterion statuses"
    return None


def check_image(iso: Path | None, boot: bool) -> dict[str, str]:
    if iso is None:
        return criterion("image", "not-run", "no --iso supplied; nothing to verify")
    if not iso.is_file():
        return criterion("image", "fail", f"{iso} does not exist")
    command = [
        sys.executable,
        "scripts/verify_live_release.py",
        "--iso",
        str(iso),
        "--compact",
    ]
    if boot:
        command.append("--boot")

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
            timeout=1200,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return criterion("image", "not-run", f"nested verifier did not complete: {exc}")

    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return criterion("image", "fail", "nested image verifier did not emit valid JSON")

    problem = _image_verdict_problem(payload, iso)
    if problem:
        return criterion("image", "fail", problem)

    overall = payload["overall"]
    if overall == "fail":
        failures = [
            f'{item["id"]}: {item["detail"]}'
            for item in payload["criteria"]
            if item["status"] == "fail"
        ]
        if completed.returncode != 1:
            return criterion("image", "fail", "nested image verifier exit code disagrees with fail verdict")
        return criterion("image", "fail", "; ".join(failures)[:300])

    if overall == "incomplete":
        if completed.returncode != 0:
            return criterion("image", "fail", "nested image verifier exit code disagrees with incomplete verdict")
        missing = [
            f'{item["id"]}: {item["detail"]}'
            for item in payload["criteria"]
            if item["status"] == "not-run"
        ]
        return criterion("image", "not-run", "; ".join(missing)[:300])

    if completed.returncode != 0:
        return criterion("image", "fail", "nested image verifier exit code disagrees with pass verdict")
    return criterion("image", "pass", "checksum, manifest, ISO structure, BIOS boot and UEFI boot passed")


def verdict(criteria: list[dict[str, str]]) -> dict[str, Any]:
    statuses = {item["status"] for item in criteria}
    if "fail" in statuses:
        overall = "fail"
    elif "not-run" in statuses:
        overall = "incomplete"
    else:
        overall = "pass"
    return {
        "schema": SCHEMA,
        "tool_version": VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "overall": overall,
        "criteria": criteria,
        "note": "incomplete is not a pass: a check that did not run proves nothing",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release-gate",
        description="Run every read-only release check and emit one verdict.",
    )
    parser.add_argument("--iso", type=Path, help="live image to verify")
    parser.add_argument("--boot", action="store_true", help="also boot the image in QEMU")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--skip-tests", action="store_true", help="for a fast structural gate")
    return parser


def exit_status(overall: str) -> int:
    """Use distinct process statuses so automation cannot confuse incomplete with pass."""
    return {"pass": 0, "fail": 1, "incomplete": 2}[overall]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    criteria = [check_docs(), check_channels()]
    if args.skip_tests:
        criteria.append(criterion("tests", "not-run", "--skip-tests was requested"))
    else:
        criteria.append(check_tests())
    criteria.append(check_evidence())
    criteria.append(check_image(args.iso, args.boot))

    result = verdict(criteria)
    rendered = json.dumps(
        result, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True
    ) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return exit_status(result["overall"])


if __name__ == "__main__":
    raise SystemExit(main())
