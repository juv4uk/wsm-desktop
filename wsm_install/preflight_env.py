# SPDX-License-Identifier: LicenseRef-Volnist
"""Check that this machine can install anything at all, before touching a disk.

The installer has many ways to fail for reasons that have nothing to do with the
target disk: a missing `mkfs.fat`, no `guix`, a `/mnt` that is already in use, a
system file that is not there. Every one of them is cheap to detect and
expensive to discover at step five of seven, after the disk has been wiped.

This module runs those checks and produces one verdict. Like every other
verdict in this repository, a check that could not run is `not-run`, and one
`not-run` makes the result `incomplete` rather than `pass`.

Nothing here writes anything. It only looks.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

SCHEMA = "wsm-install-preflight/1"


def criterion(identifier: str, status: str, detail: str) -> dict[str, str]:
    return {"id": identifier, "status": status, "detail": detail}


def check_tools(
    which: Callable[[str], str | None] = shutil.which,
    paths: Any = None,
) -> dict[str, str]:
    """Every program the install steps call must exist before the first step runs.

    `paths` is the exact list the plan will execute. Pass it whenever the plan was
    built for an image profile (`plan_steps(tool_prefixes=...)`): checking the FHS
    names instead would pass on a host that has `/usr/sbin/sgdisk` while the image
    that runs the install has no `/usr` at all. Defaulting to the tool map's paths
    keeps the host preview working, and the failure names the owning package so the
    operator knows which closure entry is missing rather than which string.
    """
    from wsm_install.tool_map import EXECUTABLES, package, name_for

    checked = sorted(paths) if paths is not None else sorted(EXECUTABLES)
    missing = [program for program in checked if which(program) is None]
    if missing:
        described = []
        for program in missing:
            owner = name_for(program)
            described.append(
                f"{program} ({package(owner)} missing)" if owner else program
            )
        return criterion(
            "tools",
            "fail",
            "missing: " + ", ".join(described) + " (the install cannot proceed)",
        )
    return criterion("tools", "pass", f"{len(checked)} programs present")


def check_guix(which: Callable[[str], str | None] = shutil.which) -> dict[str, str]:
    """The handoff step needs guix; without it the install ends half-done."""
    if which("guix") is None:
        return criterion(
            "guix",
            "fail",
            "guix is not in PATH; the system could be written but not built",
        )
    return criterion("guix", "pass", "guix is available")


def check_root(geteuid: Callable[[], int] = os.geteuid) -> dict[str, str]:
    if geteuid() != 0:
        return criterion(
            "root",
            "fail",
            "not running as root; formatting and mounting will fail",
        )
    return criterion("root", "pass", "running as root")


def check_mount_point(
    mount_point: Path,
    is_mount: Callable[[Path], bool] | None = None,
) -> dict[str, str]:
    """An already-used mount point hides the new system under an old one."""
    def default_is_mount(path: Path) -> bool:
        try:
            return os.path.ismount(path)
        except OSError:
            return False

    is_mount = is_mount or default_is_mount

    if not mount_point.exists():
        return criterion(
            "mount-point", "fail", f"{mount_point} does not exist; the root cannot be mounted"
        )
    if is_mount(mount_point):
        return criterion(
            "mount-point",
            "fail",
            f"{mount_point} is already a mount point; unmount it first, otherwise the "
            "new system is hidden under the old one",
        )
    try:
        entries = list(mount_point.iterdir())
    except OSError as exc:
        return criterion("mount-point", "fail", f"cannot read {mount_point}: {exc}")
    if entries:
        return criterion(
            "mount-point",
            "fail",
            f"{mount_point} is not empty ({len(entries)} entries); mounting over it would "
            "hide whatever is there",
        )
    return criterion("mount-point", "pass", f"{mount_point} is free")


def check_system_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return criterion("system-file", "fail", f"{path} does not exist")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return criterion("system-file", "fail", f"cannot read {path}: {exc}")
    if "operating-system" not in text:
        return criterion(
            "system-file",
            "fail",
            f"{path} does not look like a Guix system declaration",
        )
    return criterion("system-file", "pass", f"{path} declares an operating-system")


def check_report(path: Path | None) -> dict[str, str]:
    if path is None:
        return criterion("report", "not-run", "no hardware report was supplied")
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return criterion("report", "fail", f"cannot read {path}: {exc}")
    if document.get("schema_version") != "1.0.0":
        return criterion(
            "report",
            "fail",
            f"unexpected report schema {document.get('schema_version')!r}",
        )
    devices = document.get("devices") or []
    return criterion("report", "pass", f"{len(devices)} device(s) in the report")


def check_isa() -> dict[str, str]:
    """Report the CPU level; it is evidence, not a gate."""
    try:
        from wsm_hwcheck.isa import IsaError, build_evidence, read_cpuinfo_flags
        import platform

        flags, fields = read_cpuinfo_flags(Path("/proc/cpuinfo"))
        evidence = build_evidence(flags, fields, platform.machine(), "procfs:/proc/cpuinfo")
        level = evidence["levels"]["highest_supported"]
        return criterion("isa", "pass", f"highest supported level: {level}")
    except Exception as exc:  # noqa: BLE001 - the ISA check must never block an install
        return criterion("isa", "not-run", f"could not determine the ISA level: {exc}")


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
        "overall": overall,
        "criteria": criteria,
        "note": "incomplete is not a pass: a check that did not run proves nothing",
    }


def run(
    mount_point: Path = Path("/mnt"),
    system_file: Path = Path("systems/desktop.scm"),
    report: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    geteuid: Callable[[], int] = os.geteuid,
    paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    return verdict([
        check_tools(which, paths=paths),
        check_guix(which),
        check_root(geteuid),
        check_mount_point(mount_point),
        check_system_file(system_file),
        check_report(report),
        check_isa(),
    ])


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="wsm-install-preflight-env",
        description="Check that this machine can install WSM before anything is touched.",
    )
    parser.add_argument("--mount-point", type=Path, default=Path("/mnt"))
    parser.add_argument("--system-file", type=Path, default=Path("systems/desktop.scm"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    import sys

    args = build_parser().parse_args(argv)
    result = run(args.mount_point, args.system_file, args.report)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 1 if result["overall"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
