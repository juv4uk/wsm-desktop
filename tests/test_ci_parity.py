# SPDX-License-Identifier: LicenseRef-Volnist
"""Every script `make check-*` runs must also run in CI.

The repository already refuses a check target that `make check` never runs
(`tests/test_makefile_coverage.py`). This is the next step of the same idea:
a target that `make check` runs but CI never runs is a check that exists on one
machine only — and the green badge then means less than it promises.

Three scripts were in exactly that state: `check_doc_ownership.py`,
`check_profile_evidence.py` and `check_release_info.py`. Each had a companion
unittest that CI did run, so nothing was unverified — but the parity was a
coincidence, not a rule.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
CI = ROOT / ".github" / "workflows" / "ci.yml"

TARGET = re.compile(r"^(check-[a-z0-9-]+):\n((?:\t.*\n)+)", re.MULTILINE)
SCRIPT = re.compile(r"\$\(PYTHON\) (scripts/[\w./-]+\.py)")


def scripts_run_by_make_check() -> dict[str, list[str]]:
    """Script path -> the check targets that invoke it."""
    found: dict[str, list[str]] = {}
    text = MAKEFILE.read_text(encoding="utf-8")
    for match in TARGET.finditer(text):
        target, body = match.group(1), match.group(2)
        for script in SCRIPT.findall(body):
            found.setdefault(script, []).append(target)
    return found


class CiParityTests(unittest.TestCase):
    def test_every_make_check_script_runs_in_ci(self) -> None:
        ci = CI.read_text(encoding="utf-8")
        missing = {
            script: targets
            for script, targets in scripts_run_by_make_check().items()
            if script not in ci
        }
        self.assertEqual(
            missing,
            {},
            "these scripts run in `make check` but never in CI: "
            + ", ".join(f"{script} ({', '.join(targets)})" for script, targets in missing.items()),
        )

    def test_the_audit_finds_something(self) -> None:
        """If the parser stops matching, the test above would pass vacuously."""
        self.assertGreaterEqual(len(scripts_run_by_make_check()), 4)


if __name__ == "__main__":
    unittest.main()
