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
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_LOCKS = {
    "free": ROOT / "channels.lock.scm",
    "compatibility": ROOT / "channels" / "compatibility.lock.scm",
}

SCHEMA = "wsm-release-gate/1"
VERSION = "0.1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def check_channels(product: str) -> dict[str, str]:
    """Validate only the products selected for this release artifact."""
    selected = {
        "free": ("free",),
        "compatibility": ("compatibility",),
        "all": ("free", "compatibility"),
    }
    if product not in selected:
        return criterion("channels", "fail", f"unsupported product selection: {product!r}")

    results: list[tuple[str, str, str]] = []
    for policy in selected[product]:
        lock = CHANNEL_LOCKS[policy]
        if not lock.is_file():
            if policy == "free":
                results.append(("free", "fail", f"required Free lock is missing: {lock.name}"))
            else:
                results.append(("compatibility", "not-run", "Compatibility lock NOT_CONFIGURED"))
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
        results.append((policy, status, f"structural policy: {detail}"))
        if status != "pass":
            continue

        # Structural validation pins the expected introduction metadata but
        # does not verify signatures. Guix must independently authenticate and
        # resolve the exact lock before a release can claim channel trust.
        auth_code, auth_detail = run(
            [
                "guix",
                "time-machine",
                "-C",
                str(lock),
                "--",
                "describe",
                "-f",
                "channels",
            ],
            timeout=900,
        )
        auth_status = "pass" if auth_code == 0 else "not-run" if auth_code == 127 else "fail"
        results.append((f"{policy}-authentication", auth_status, auth_detail))

    failures = [f"{policy}: {detail}" for policy, status, detail in results if status == "fail"]
    if failures:
        return criterion("channels", "fail", "; ".join(failures))
    not_run = [f"{policy}: {detail}" for policy, status, detail in results if status == "not-run"]
    if not_run:
        return criterion("channels", "not-run", "; ".join(not_run))
    return criterion(
        "channels",
        "pass",
        f"{product} product channel lock policy passed; no other product is implied",
    )


def check_tests() -> dict[str, str]:
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    if not tests:
        return criterion("tests", "not-run", "no test files found")
    code, detail = run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        timeout=900,
    )
    if code == 127:
        return criterion("tests", "not-run", detail)
    if code != 0:
        return criterion("tests", "fail", detail)
    return criterion("tests", "pass", f"unittest discovery passed across {len(tests)} test modules")


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

    if not isinstance(payload, dict) or payload.get("schema") != "wsm-release-verdict/1":
        return criterion("image", "fail", "live image verifier returned an unknown or missing schema")
    if payload.get("artifact") != iso.name:
        return criterion("image", "fail", "live image verifier verdict names a different ISO artifact")
    try:
        actual_sha256 = sha256_file(iso)
    except OSError as exc:
        return criterion("image", "fail", f"cannot hash selected ISO: {exc}")
    if payload.get("artifact_sha256") != actual_sha256:
        return criterion(
            "image",
            "fail",
            "live image verifier SHA-256 does not match the selected ISO bytes",
        )

    expected_ids = {"checksum", "manifest", "iso-structure", "boot-bios", "boot-uefi"}
    criteria = payload.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return criterion("image", "fail", "live image verifier returned no criteria")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("status"), str)
        or item.get("status") not in {"pass", "fail", "not-run"}
        or not isinstance(item.get("detail"), str)
        for item in criteria
    ):
        return criterion("image", "fail", "live image verifier returned malformed criteria")
    identifiers = [item["id"] for item in criteria]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != expected_ids:
        return criterion("image", "fail", "live image verifier criteria do not match the required set")

    statuses = {item["status"] for item in criteria}
    expected_overall = "fail" if "fail" in statuses else "incomplete" if "not-run" in statuses else "pass"
    overall = payload.get("overall")
    expected_exit = {"pass": 0, "fail": 1, "incomplete": 2}[expected_overall]
    if overall != expected_overall or completed.returncode != expected_exit:
        return criterion(
            "image",
            "fail",
            f"verifier result is inconsistent: exit={completed.returncode}, reported={overall!r}, expected={expected_overall!r}",
        )

    if overall == "pass":
        return criterion("image", "pass", "checksum, manifest, ISO structure and both boot checks passed")
    if overall == "incomplete":
        pending = [
            f"{item['id']}: {item.get('detail', '')}"
            for item in criteria
            if item["status"] == "not-run"
        ]
        return criterion("image", "not-run", "; ".join(pending)[:300] or "live image verification is incomplete")
    failed = [
        f"{item['id']}: {item.get('detail', '')}"
        for item in criteria
        if item["status"] == "fail"
    ]
    return criterion("image", "fail", "; ".join(failed)[:300] or "live image verifier reported failure")


def verdict(criteria: list[dict[str, str]], product: str) -> dict[str, Any]:
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
        "product": product,
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
    parser.add_argument(
        "--product",
        choices=("free", "compatibility", "all"),
        required=True,
        help="product whose channel policy this release verdict covers",
    )
    parser.add_argument("--iso", type=Path, help="live image to verify")
    parser.add_argument("--boot", action="store_true", help="also boot the image in QEMU")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--skip-tests", action="store_true", help="for a fast structural gate")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    criteria = [check_docs(), check_channels(args.product)]
    if args.skip_tests:
        criteria.append(criterion("tests", "not-run", "--skip-tests was requested"))
    else:
        criteria.append(check_tests())
    criteria.append(check_evidence())
    criteria.append(check_image(args.iso, args.boot))

    result = verdict(criteria, args.product)
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
