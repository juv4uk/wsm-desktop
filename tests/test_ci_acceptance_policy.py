# SPDX-License-Identifier: LicenseRef-Volnist
"""Hosted CI stays deliberately small; integration acceptance is manual."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release-minimal-live.yml"
MAKEFILE_PATH = ROOT / "Makefile"


class CiAcceptancePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.workflow = yaml.load(cls.workflow_text, Loader=yaml.BaseLoader)

    def test_only_fast_checks_run_in_hosted_ci(self) -> None:
        self.assertEqual(set(self.workflow["jobs"]), {"checks"})
        job = self.workflow["jobs"]["checks"]
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertLessEqual(int(job["timeout-minutes"]), 10)

    def test_ci_runs_for_main_pushes_and_pull_requests(self) -> None:
        events = self.workflow["on"]
        self.assertEqual(events["push"]["branches"], ["main"])
        self.assertIn("pull_request", events)
        self.assertNotIn("workflow_dispatch", events)
        self.assertNotIn("paths", events["push"])
        self.assertNotIn("paths", events["pull_request"] or {})

    def test_ci_runs_tests_docs_and_channel_policy(self) -> None:
        steps = self.workflow["jobs"]["checks"]["steps"]
        commands = " ".join(step.get("run", "") for step in steps)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py' -v", commands)
        self.assertIn("python scripts/check_docs.py", commands)
        self.assertIn("--lock channels.lock.scm --policy free", commands)
        self.assertIn("--lock channels/compatibility.lock.scm --policy compatibility", commands)

    def test_slow_or_environmental_acceptance_is_not_in_hosted_ci(self) -> None:
        forbidden = (
            "qemu-system",
            "qemu-acceptance",
            "grub-mkrescue",
            "apt-get",
            "guix-install.sh",
            "workflow_dispatch",
            "acceptance-gates",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.workflow_text)

    def test_ci_has_read_only_permissions_and_no_secrets(self) -> None:
        self.assertEqual(self.workflow["permissions"]["contents"], "read")
        self.assertNotIn("secrets.", self.workflow_text)

    def test_slow_qemu_checks_remain_available_as_manual_commands(self) -> None:
        makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("qemu-acceptance-manual:", makefile)
        for script in (
            "scripts/ci_qemu_guest_smoke.sh",
            "scripts/ci_qemu_hwcheck_guest.py",
            "scripts/ci_cxl_qemu_guest.py",
        ):
            with self.subTest(script=script):
                self.assertIn(script, makefile)
        aggregate = next(
            line.split(":", 1)[1].split()
            for line in makefile.splitlines()
            if line.startswith("check:")
        )
        self.assertNotIn("qemu-acceptance-manual", aggregate)



class ReleaseAcceptanceTimeoutTests(unittest.TestCase):
    """A hung acceptance step must not be able to eat the whole release budget.

    qemu_boot_smoke.py bounds its own serial read (--timeout-seconds), but the
    release job ceiling is six hours. On 2026-11-28 the RC5 draft sat in "BIOS boot
    acceptance" for hours with no diagnosis: either the kill path did not take
    effect or the runner stopped reporting, and nothing at the workflow level
    bounded the step. The step-level timeout is the fail-closed backstop: the
    release fails with a diagnostic inside the job budget instead of hanging.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.load(
            RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )

    def _steps(self) -> list[dict]:
        jobs = self.workflow["jobs"]
        self.assertIn("build-and-publish", jobs)
        return jobs["build-and-publish"]["steps"]

    def test_release_job_keeps_a_bounded_ceiling(self) -> None:
        job = self.workflow["jobs"]["build-and-publish"]
        self.assertLessEqual(int(job["timeout-minutes"]), 360)

    def test_every_qemu_acceptance_step_bounds_itself(self) -> None:
        qemu_steps = [
            step for step in self._steps()
            if "qemu_boot_smoke.py" in (step.get("run") or "")
        ]
        self.assertTrue(
            qemu_steps,
            "the release workflow no longer runs the QEMU boot smoke; update this test",
        )
        for step in qemu_steps:
            name = step.get("name", "<unnamed>")
            self.assertIn(
                "timeout-minutes", step,
                f"acceptance step {name!r} has no step-level timeout; a hung QEMU "
                "would consume the six-hour job budget",
            )
            self.assertLessEqual(
                int(step["timeout-minutes"]), 15,
                f"acceptance step {name!r} may not wait longer than 15 minutes",
            )

class PackageArchiveWorkflowTests(unittest.TestCase):
    """Legacy archive entry is read-only; binary publication uses scoped H170 lanes."""

    WORKFLOW = ROOT / ".github" / "workflows" / "package-archives.yml"

    def setUp(self) -> None:
        self.text = self.WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)

    def test_the_fixed_plan_job_is_enabled_on_main(self) -> None:
        job = self.workflow["jobs"]["plan"]
        self.assertNotEqual(job.get("if"), "${{ false }}")
        self.assertEqual(job["if"], "${{ github.ref == 'refs/heads/main' }}")

    def test_workflow_is_manual_only_and_read_only(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertNotIn("ВЛАСНИК ДАВ ДОЗВІЛ", self.text)

    def test_only_the_fixed_h170_free_manifest_is_evaluated(self) -> None:
        steps = self.workflow["jobs"]["plan"]["steps"]
        plan = next(step for step in steps if step.get("name") == "Evaluate the fixed H170 Free package plan")
        self.assertIn("guix time-machine -C channels.lock.scm", plan["run"])
        self.assertIn("--dry-run --no-grafts", plan["run"])
        self.assertIn("--manifest=drivers/profiles/h170-free-packages.scm", plan["run"])
        self.assertNotIn("wsm-tools", plan["run"])
        self.assertNotIn("inputs", plan["run"])

    def test_no_arbitrary_shell_input_or_binary_export_remains(self) -> None:
        for forbidden in (
            "inputs:",
            "github.event.inputs",
            "${{ inputs.",
            "packages-*",
            "*[!A-Za-z0-9._+-]*",
            "actions/upload-artifact",
            "guix archive --export",
            "gh release",
            "guix publish",
            "GH_TOKEN",
            "contents: write",
            "pages: write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)

    def test_the_fixed_h170_substitute_lane_remains_separate(self) -> None:
        substitutes = (ROOT / ".github" / "workflows" / "substitutes.yml").read_text(encoding="utf-8")
        self.assertIn("drivers/profiles/h170-free-packages.scm", substitutes)
        self.assertIn("guix publish", substitutes)


class StartupBenchmarkTests(unittest.TestCase):
    """The cost of starting the installer must be measurable, not argued about."""

    SCRIPT = ROOT / "scripts" / "bench_installer_startup.py"

    def test_the_benchmark_exists_and_measures_three_things(self) -> None:
        text = self.SCRIPT.read_text(encoding="utf-8")
        for expected in ("interpreter floor", "entry point import", "wsm-install --version"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_it_can_compare_a_compiled_candidate(self) -> None:
        self.assertIn("--compare", self.SCRIPT.read_text(encoding="utf-8"))

    def test_it_reports_and_does_not_gate(self) -> None:
        """A threshold nobody agreed to is how a measurement becomes a flaky gate."""
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("It reports; it never fails a build", text)
        self.assertNotIn("sys.exit(1)", text)

    def test_it_refuses_a_meaningless_sample_size(self) -> None:
        self.assertIn("--runs below 3 is noise", self.SCRIPT.read_text(encoding="utf-8"))


class FreePascalBuildTests(unittest.TestCase):
    """All four native Pascal executables must compile and be checked at runtime."""

    WORKFLOW = ROOT / ".github" / "workflows" / "fpc-build.yml"

    def setUp(self) -> None:
        self.text = self.WORKFLOW.read_text(encoding="utf-8")

    def test_the_toolchain_and_fcl_version_are_pinned_and_checked(self) -> None:
        self.assertIn("fp-compiler-3.2.2", self.text)
        self.assertIn("fp-units-fcl-3.2.2", self.text)
        self.assertIn('test "$(fpc -iV)" = "3.2.2"', self.text)

    def test_it_compiles_all_four_pascal_programs_from_the_makefile(self) -> None:
        self.assertIn("make -C tools/pascal clean all", self.text)
        self.assertIn("test -x tools/pascal/build/wsm-hwcheck", self.text)
        self.assertIn("test -x tools/pascal/build/wsm-classify", self.text)
        self.assertIn("test -x tools/pascal/build/wsm-partition", self.text)
        self.assertIn("test -x tools/pascal/build/wsm-profile", self.text)
        self.assertNotIn("git ls-files '*.lpr'", self.text)

    def test_a_compile_or_parity_error_fails_the_run(self) -> None:
        self.assertIn("make -C tools/pascal clean all", self.text)
        self.assertIn("python3 tests/test_fpc_package.py", self.text)
        self.assertIn("python3 tests/test_fpc_profile.py", self.text)
        self.assertIn("if: failure()", self.text)
        self.assertIn("Report compiler or parity failure", self.text)

    def test_the_workflow_does_not_report_success_without_all_four_binaries(self) -> None:
        self.assertIn("test -x tools/pascal/build/wsm-hwcheck", self.text)
        self.assertIn("test -x tools/pascal/build/wsm-classify", self.text)
        self.assertIn("test -x tools/pascal/build/wsm-partition", self.text)
        self.assertIn("test -x tools/pascal/build/wsm-profile", self.text)
        self.assertNotIn("WSM_FPC_PROGRAMS=0", self.text)



class PascalSourceContractTests(unittest.TestCase):
    """fpc accepts a file with no licence, no mode and a mismatched name. This does not."""

    SCRIPT = ROOT / "scripts" / "check_pascal_sources.py"

    def setUp(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("check_pascal_sources", self.SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.module)

    def write(self, name: str, text: str) -> "object":
        import tempfile
        from pathlib import Path as _Path

        directory = tempfile.mkdtemp()
        path = _Path(directory) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_conforming_unit_passes(self) -> None:
        path = self.write(
            "demo.pas",
            "// SPDX-License-Identifier: LicenseRef-Volnist\n"
            "unit demo;\n{$mode objfpc}\ninterface\nimplementation\nend.\n",
        )
        self.assertEqual(self.module.check(path), [])

    def test_a_missing_licence_line_is_named(self) -> None:
        path = self.write("demo.pas", "unit demo;\n{$mode objfpc}\nend.\n")
        self.assertTrue(any("LicenseRef-Volnist" in p for p in self.module.check(path)))

    def test_a_missing_mode_directive_is_named(self) -> None:
        path = self.write(
            "demo.pas",
            "// SPDX-License-Identifier: LicenseRef-Volnist\nunit demo;\nend.\n",
        )
        self.assertTrue(any("{$mode" in p for p in self.module.check(path)))

    def test_a_unit_named_after_another_file_is_named(self) -> None:
        path = self.write(
            "demo.pas",
            "// SPDX-License-Identifier: LicenseRef-Volnist\n"
            "unit other;\n{$mode objfpc}\nend.\n",
        )
        self.assertTrue(any("declares 'other'" in p for p in self.module.check(path)))

    def test_a_debug_block_on_stdout_is_named(self) -> None:
        path = self.write(
            "demo.pas",
            "// SPDX-License-Identifier: LicenseRef-Volnist\n"
            "unit demo;\n{$mode objfpc}\n{$ifdef DEBUG}writeln('x');{$endif}\nend.\n",
        )
        self.assertTrue(any("DEBUG" in p for p in self.module.check(path)))

    def test_an_empty_tree_is_not_a_failure(self) -> None:
        """The check runs before any Pascal exists; it must not block the tree."""
        self.assertIn("no Pascal sources yet", self.SCRIPT.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
