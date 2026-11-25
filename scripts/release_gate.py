# SPDX-License-Identifier: LicenseRef-Volnist
"""One command that answers: can this be shipped?

A release is not a moment when someone remembers to run five checks. It is the
point where every check has already passed, and somebody can point at the
result.

This gate runs the checks that exist and produces a single verdict. It is
deliberately conservative:

* a check that could not run is `not-run`, never a pass - and one `not-run`
  makes the whole verdict `incomplete`, not `pass`;
* it never runs a check that writes anything: every step here is read-only;
* it reports what it did not verify, so an empty criteria list cannot be
  mistaken for a clean bill of health.

The gate does not replace judgement. It removes the excuse of not knowing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_channels import default_lock

SCHEMA = "wsm-release-gate/1"
VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], timeout: int = 900) -> tuple[int, str]:
    """Run a read-only check and return (returncode, last meaningful line)."""
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, cwd=ROOT, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        return 124, f"timed out while running {command[0]} after {timeout}s"
    except OSError as exc:
        return 127, f"could not run {command[0]}: {exc}"
    output = (completed.stdout + completed.stderr).strip().splitlines()
    tail = output[-1] if output else "no output"
    return completed.returncode, tail[:300]


def criterion(identifier: str, status: str, detail: str) -> dict[str, str]:
    return {"id": identifier, "status": status, "detail": detail}


def from_exit(identifier: str, code: int, detail: str) -> dict[str, str]:
    if code == 127:
        return criterion(identifier, "not-run", detail)
    return criterion(identifier, "pass" if code == 0 else "fail", detail)


def check_docs() -> dict[str, str]:
    code, detail = run([sys.executable, "scripts/check_docs.py"])
    return from_exit("docs", code, detail)


def check_channels() -> dict[str, str]:
    """Check required Free lock and report an absent optional Compatibility lock honestly."""
    results: list[tuple[str, str, str]] = []
    for policy in ("free", "compatibility"):
        lock = default_lock(policy)
        if not lock.is_file():
            if policy == "free":
                results.append(("free", "fail", f"required Free lock is missing: {lock.name}"))
            else:
                results.append(
                    ("compatibility", "not-run", "Compatibility lock NOT_CONFIGURED")
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
        status = "pass" if code == 0 else "not-run" if code == 127 else "fail"
        results.append((policy, status, detail))

    failures = [f"{policy}: {detail}" for policy, status, detail in results if status == "fail"]
    if failures:
        return criterion("channels", "fail", "; ".join(failures))
    not_run = [f"{policy}: {detail}" for policy, status, detail in results if status == "not-run"]
    if not_run:
        return criterion("channels", "not-run", "; ".join(not_run))
    return criterion("channels", "pass", "Free and configured Compatibility locks satisfy structural policy")


def check_tests() -> dict[str, str]:
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    if not tests:
        return criterion("tests", "not-run", "no test files found")
    failures: list[str] = []
    not_run: list[str] = []
    for path in tests:
        code, detail = run([sys.executable, str(path)])
        if code == 127:
            not_run.append(f"{path.name}: {detail}")
        elif code != 0:
            failures.append(f"{path.name}: {detail}")
    if failures:
        return criterion("tests", "fail", "; ".join(failures)[:300])
    if not_run:
        return criterion("tests", "not-run", "; ".join(not_run)[:300])
    return criterion("tests", "pass", f"{len(tests)} test files green")


def check_evidence() -> dict[str, str]:
    code, detail = run([sys.executable, "scripts/check_profile_evidence.py"])
    if code == 0 and "no evidence bundles yet" in detail:
        return criterion("profile-evidence", "not-run", "no hardware profile bundles exist yet")
    return from_exit("profile-evidence", code, detail)


def check_image(iso: Path | None, boot: bool) -> dict[str, str]:
    if iso is None:
        return criterion("image", "not-run", "no --iso supplied; nothing to verify")
    if not iso.is_file():
        return criterion("image", "fail", f"{iso} does not exist")
    command = [sys.executable, "scripts/verify_live_release.py", "--iso", str(iso), "--compact"]
    if boot:
        command.append("--boot")
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, cwd=ROOT, timeout=900
        )
    except subprocess.TimeoutExpired:
        return criterion("image", "not-run", "live image verification timed out")
    except OSError as exc:
        return criterion("image", "not-run", f"could not run live image verifier: {exc}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        return criterion("image", "fail", (detail[-1] if detail else "verifier emitted invalid JSON")[:300])

    overall = payload.get("overall") if isinstance(payload, dict) else None
    if completed.returncode == 0 and overall == "pass":
        return criterion("image", "pass", "checksum, manifest, ISO structure and requested boot checks passed")
    if completed.returncode == 2 and overall == "incomplete":
        pending = [
            f"{item.get('id')}: {item.get('detail')}"
            for item in payload.get("criteria", [])
            if isinstance(item, dict) and item.get("status") == "not-run"
        ]
        return criterion("image", "not-run", "; ".join(pending)[:300] or "live image verification is incomplete")
    if completed.returncode == 1 and overall == "fail":
        failed = [
            f"{item.get('id')}: {item.get('detail')}"
            for item in payload.get("criteria", [])
            if isinstance(item, dict) and item.get("status") == "fail"
        ]
        return criterion("image", "fail", "; ".join(failed)[:300] or "live image verifier reported failure")
    return criterion(
        "image",
        "fail",
        f"verifier exit/status mismatch: exit={completed.returncode}, overall={overall!r}",
    )


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
    return {"pass": 0, "fail": 1, "incomplete": 2}[result["overall"]]


if __name__ == "__main__":
    raise SystemExit(main())
