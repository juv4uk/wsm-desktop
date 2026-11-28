# SPDX-License-Identifier: LicenseRef-Volnist
"""The remote release verifier must reject partial, changed and unsafe assets."""

from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publication_state  # noqa: E402
from verify_release_assets import ReleaseAssetError, verify_release_assets  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_bundle(root: Path) -> tuple[Path, Path]:
    expected = root / "expected"
    downloaded = root / "downloaded"
    expected.mkdir()
    downloaded.mkdir()
    assets = {
        "wsm.iso": b"iso-image-bytes",
        "build-manifest.json": b'{"schema":"build/1"}\n',
        "release-manifest.json": b'{"schema":"release/1"}\n',
        "boot-bios.json": b'{"boot_confirmed":true}\n',
        "boot-uefi.json": b'{"boot_confirmed":true}\n',
    }
    for name, content in assets.items():
        (expected / name).write_bytes(content)
        (downloaded / name).write_bytes(content)
    sums = "".join(f"{digest(content)}  {name}\n" for name, content in sorted(assets.items()))
    (expected / "SHA256SUMS").write_text(sums, encoding="utf-8")
    (downloaded / "SHA256SUMS").write_text(sums, encoding="utf-8")
    # Local notes are deliberately not release assets and are not listed.
    (expected / "RELEASE-NOTES.md").write_text("release notes", encoding="utf-8")
    return expected, downloaded


class ReleaseAssetVerificationTests(unittest.TestCase):
    def test_release_workflow_attests_every_asset_after_readback(self) -> None:
        import yaml

        workflow_path = ROOT / ".github" / "workflows" / "release-minimal-live.yml"
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        permissions = workflow["permissions"]
        for permission in ("contents", "id-token", "attestations"):
            with self.subTest(permission=permission):
                self.assertEqual(permissions[permission], "write")
        self.assertNotIn("artifact-metadata", permissions)

        steps = workflow["jobs"]["build-and-publish"]["steps"]
        names = [step.get("name", "") for step in steps]
        request = steps[names.index("Перевірити запит релізу")]["run"]
        self.assertIn('if [ "$GITHUB_REF" != "refs/heads/main" ]', request)
        attest_index = names.index("Підписати provenance релізних артефактів")
        gh_version_index = names.index("Перевірити версію GitHub CLI для перевірки provenance")
        verify_index = names.index("Перевірити provenance артефактів перед публікацією")
        readback = names.index("Перевірити завантажені assets до публікації")
        publish = names.index("Опублікувати перевірений GitHub pre-release")
        self.assertLess(readback, attest_index)
        self.assertLess(attest_index, gh_version_index)
        self.assertLess(gh_version_index, verify_index)
        self.assertLess(verify_index, publish)
        version_check = steps[gh_version_index]["run"]
        self.assertIn("gh version", version_check)
        self.assertIn("2.102.0", version_check)
        self.assertIn("sort -V", version_check)
        self.assertIn('echo "GitHub CLI: $GH_VERSION"', version_check)
        self.assertIn('>> "$GITHUB_STEP_SUMMARY"', version_check)

        attest = steps[attest_index]
        self.assertEqual(attest["uses"], "actions/attest@v4")
        self.assertIs(attest["with"]["create-storage-record"], False)
        subjects = attest["with"]["subject-path"]
        self.assertEqual(subjects, "${{ steps.attestation-subjects.outputs.paths }}")

        verification = steps[verify_index]["run"]
        self.assertIn("gh attestation verify", verification)
        self.assertIn('--repo "$GITHUB_REPOSITORY"', verification)
        self.assertIn("--bundle", verification)
        self.assertIn("bundle-path", verification)
        self.assertIn('mapfile -t SUBJECTS < "$SUBJECT_FILE"', verification)
        self.assertIn('test "${#SUBJECTS[@]}" -eq "$EXPECTED_COUNT"', verification)
        self.assertIn('test "$VERIFIED_COUNT" -eq "$EXPECTED_COUNT"', verification)
        self.assertIn("--signer-workflow", verification)
        self.assertIn("--source-ref refs/heads/main", verification)
        self.assertIn("release-minimal-live.yml", verification)
        self.assertIn("https://slsa.dev/provenance/v1", verification)

    def test_valid_download_matches_local_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            result = verify_release_assets(expected, downloaded)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["verified_asset_count"], 5)
        self.assertEqual(
            [item["name"] for item in result["assets"]],
            ["boot-bios.json", "boot-uefi.json", "build-manifest.json", "release-manifest.json", "wsm.iso"],
        )

    def test_changed_remote_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "wsm.iso").write_bytes(b"truncated remote bytes")
            with self.assertRaisesRegex(ReleaseAssetError, "checksum mismatch"):
                verify_release_assets(expected, downloaded)

    def test_missing_remote_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "boot-uefi.json").unlink()
            with self.assertRaisesRegex(ReleaseAssetError, "asset set differs"):
                verify_release_assets(expected, downloaded)

    def test_extra_remote_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "unexpected.bin").write_bytes(b"unexpected")
            with self.assertRaisesRegex(ReleaseAssetError, "asset set differs"):
                verify_release_assets(expected, downloaded)

    def test_checksum_manifest_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            (downloaded / "SHA256SUMS").write_text("0" * 64 + "  wsm.iso\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseAssetError, "SHA256SUMS differs"):
                verify_release_assets(expected, downloaded)

    def test_path_traversal_in_checksum_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected, downloaded = make_bundle(Path(temporary))
            sums = (expected / "SHA256SUMS").read_text(encoding="utf-8")
            (expected / "SHA256SUMS").write_text(sums + "0" * 64 + "  ../escape.bin\n", encoding="utf-8")
            (downloaded / "SHA256SUMS").write_text((expected / "SHA256SUMS").read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ReleaseAssetError, "unsafe"):
                verify_release_assets(expected, downloaded)

    def test_symlink_in_download_directory_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected, downloaded = make_bundle(root)
            target = downloaded / "wsm.iso"
            target.unlink()
            target.symlink_to(expected / "wsm.iso")
            with self.assertRaisesRegex(ReleaseAssetError, "non-regular"):
                verify_release_assets(expected, downloaded)


class PublicationStateTests(unittest.TestCase):
    """`scripts/publication_state.py` answers "published? matching?" from gh JSON.

    Every test feeds recorded GitHub CLI output, so none of them need a network,
    a token or an authenticated `gh`.
    """

    ISO = "WSM-Desktop-0.1.0-rc9-Minimal-Live.iso"
    TAG = "0.1.0-rc9-minimal-live"

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.root = self.directory / "repo"
        self.root.mkdir()
        (self.root / "RELEASE-REQUEST.txt").write_text(
            f"# requested build\n{self.TAG}\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._temporary.cleanup()

    # -- fixtures ---------------------------------------------------------

    @staticmethod
    def asset(name: str, size: int = 1024) -> dict[str, object]:
        return {
            "name": name,
            "size": size,
            "state": "uploaded",
            "digest": "sha256:" + hashlib.sha256(name.encode("utf-8")).hexdigest(),
        }

    def complete_assets(self) -> list[dict[str, object]]:
        return [
            self.asset(name)
            for name in (
                "SHA256SUMS",
                "build-manifest.json",
                "release-manifest.json",
                "boot-bios.json",
                "boot-uefi.json",
                "build.log",
                "channels.resolved.scm",
                "channel-resolution.log",
                self.ISO,
            )
        ]

    def release_detail(
        self,
        assets: list[dict[str, object]],
        draft: bool = False,
        tag: str | None = None,
    ) -> dict[str, object]:
        tag = tag or self.TAG
        return {
            "tagName": tag,
            "name": f"WSM Desktop {tag}",
            "isDraft": draft,
            "isPrerelease": True,
            "publishedAt": "0001-01-01T00:00:00Z" if draft else "2026-11-28T06:20:17Z",
            "createdAt": "2026-11-28T01:56:59Z",
            "targetCommitish": "1fa19879ec780e372cce9a4bb4c13f613d01ec9f",
            "url": f"https://github.com/juv4uk/wsm-desktop/releases/tag/{tag}",
            "assets": assets,
        }

    def write_json(self, name: str, payload: object) -> Path:
        path = self.directory / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def offline_argv(self, details: list[dict[str, object]]) -> list[str]:
        listing = [
            {
                "tagName": detail["tagName"],
                "name": detail["name"],
                "isDraft": detail["isDraft"],
                "isPrerelease": detail["isPrerelease"],
                "publishedAt": detail["publishedAt"],
                "createdAt": detail["createdAt"],
            }
            for detail in details
        ]
        argv = [
            "--releases-json",
            str(self.write_json("releases.json", listing)),
            "--root",
            str(self.root),
        ]
        for index, detail in enumerate(details):
            argv += [
                "--release-json",
                str(self.write_json(f"release-{index}.json", detail)),
            ]
        return argv

    def checksums_file(self, assets: list[dict[str, object]]) -> Path:
        lines = []
        for asset in assets:
            name = str(asset["name"])
            if name == "SHA256SUMS":
                continue
            digest_value = hashlib.sha256(name.encode("utf-8")).hexdigest()
            lines.append(f"{digest_value}  {name}\n")
        path = self.directory / "SHA256SUMS"
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = publication_state.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    # -- the five cases the owner needs -----------------------------------

    def test_complete_published_release_passes(self) -> None:
        assets = self.complete_assets()
        argv = self.offline_argv([self.release_detail(assets)])
        argv += ["--checksums", str(self.checksums_file(assets)), "--json"]
        code, stdout, stderr = self.run_cli(argv)

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        self.assertEqual(report["verdict"], "match")
        self.assertEqual(report["problems"], [])
        release = report["releases"][0]
        self.assertEqual(release["state"], "published")
        self.assertTrue(release["published"])
        self.assertEqual(release["missing_required"], [])
        self.assertEqual(release["missing_supporting"], [])
        self.assertEqual(release["extras"], [])
        self.assertEqual(release["image_form"], "whole")
        self.assertEqual(release["asset_count"], 9)
        self.assertEqual(
            sorted(
                asset["name"]
                for asset in release["assets"]
                if asset["checksum"] == "listed"
            ),
            sorted(asset["name"] for asset in assets if asset["name"] != "SHA256SUMS"),
        )
        self.assertEqual(report["requested_tag"]["status"], "published")

    def test_missing_expected_asset_is_named(self) -> None:
        assets = [
            asset for asset in self.complete_assets() if asset["name"] != "boot-uefi.json"
        ]
        argv = self.offline_argv([self.release_detail(assets)])
        argv += ["--checksums", str(self.checksums_file(assets)), "--json"]
        code, stdout, stderr = self.run_cli(argv)

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        release = report["releases"][0]
        self.assertEqual(release["missing_required"], ["boot-uefi.json"])
        self.assertEqual(report["verdict"], "mismatch")
        self.assertTrue(
            any("boot-uefi.json" in problem for problem in report["problems"]),
            report["problems"],
        )

        failing = self.run_cli(argv[:-1] + ["--fail-on-mismatch"])
        self.assertEqual(failing[0], 1, "an expected-but-absent asset must fail the gate")

    def test_unexpected_extra_asset_is_reported_but_not_fatal(self) -> None:
        assets = self.complete_assets() + [self.asset("release-notes.txt", 42)]
        argv = self.offline_argv([self.release_detail(assets)])
        argv += ["--checksums", str(self.checksums_file(assets)), "--json"]
        code, stdout, stderr = self.run_cli(argv)

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        release = report["releases"][0]
        self.assertEqual(release["extras"], ["release-notes.txt"])
        self.assertEqual(release["missing_required"], [])
        self.assertEqual(report["problems"], [], "an extra asset is not a defect")
        self.assertEqual(report["verdict"], "match")

        text = self.run_cli(argv[:-1])[1]
        self.assertIn("release-notes.txt", text)
        self.assertIn("not fatal", text)

    def test_draft_is_reported_as_not_published(self) -> None:
        assets = [asset for asset in self.complete_assets() if asset["name"] != "build.log"]
        argv = self.offline_argv([self.release_detail(assets, draft=True)])
        argv += ["--json"]
        code, stdout, stderr = self.run_cli(argv)

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        release = report["releases"][0]
        self.assertEqual(release["state"], "draft")
        self.assertFalse(release["published"])
        self.assertEqual(report["requested_tag"]["status"], "draft")
        self.assertEqual(
            report["problems"],
            [],
            "a draft's incomplete asset list is unknown, not missing",
        )
        self.assertEqual(release["missing_supporting"], ["build.log"])
        kinds = {item["what"]: item["kind"] for item in release["unknowns"]}
        self.assertIn("asset completeness of draft " + self.TAG, kinds)
        self.assertEqual(kinds["asset completeness of draft " + self.TAG], "unresolved")

        text = self.run_cli(argv[:-1])[1]
        self.assertIn("DRAFT — not published", text)

    def test_malformed_gh_response_produces_a_clear_error(self) -> None:
        cases = {
            "not JSON": "{this is not json",
            "assets not a list": json.dumps(
                {**self.release_detail(self.complete_assets()), "assets": "none"}
            ),
            "asset without a name": json.dumps(
                {
                    **self.release_detail([]),
                    "assets": [{"size": 10, "state": "uploaded"}],
                }
            ),
            "size not an integer": json.dumps(
                {
                    **self.release_detail([]),
                    "assets": [{"name": "x.iso", "size": "big"}],
                }
            ),
            "list not an array": json.dumps({"tagName": self.TAG}),
        }
        for label, payload in cases.items():
            with self.subTest(label):
                detail_path = self.directory / "broken.json"
                detail_path.write_text(payload, encoding="utf-8")
                listing = self.write_json(
                    "releases.json",
                    [
                        {
                            "tagName": self.TAG,
                            "name": "n",
                            "isDraft": False,
                            "isPrerelease": True,
                            "publishedAt": "2026-11-28T06:20:17Z",
                            "createdAt": "2026-11-28T01:56:59Z",
                        }
                    ],
                )
                code, _, stderr = self.run_cli(
                    [
                        "--releases-json", str(listing),
                        "--release-json", str(detail_path),
                        "--root", str(self.root),
                    ]
                )
                self.assertEqual(code, 2, stderr)
                self.assertIn("publication-state:", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertTrue(stderr.strip().splitlines()[-1].strip())

    def test_checksum_presence_is_unknown_without_the_manifest(self) -> None:
        """The manifest is an asset, not metadata: without it, say unknown."""
        assets = self.complete_assets()
        argv = self.offline_argv([self.release_detail(assets)]) + ["--json"]
        code, stdout, stderr = self.run_cli(argv)

        self.assertEqual(code, 0, stderr)
        report = json.loads(stdout)
        release = report["releases"][0]
        statuses = {asset["name"]: asset["checksum"] for asset in release["assets"]}
        self.assertEqual(statuses["SHA256SUMS"], "manifest")
        self.assertEqual(statuses[self.ISO], "unknown")
        self.assertEqual(report["verdict"], "match-with-unknowns")
        self.assertTrue(
            any(
                item["what"] == "whether a checksum is published for each asset"
                for item in release["unknowns"]
            ),
            release["unknowns"],
        )

    def test_the_tool_can_only_read(self) -> None:
        """The read-only promise is a property of the code, not of the docs."""
        self.assertEqual(
            publication_state.READ_ONLY_COMMANDS, ("release list", "release view")
        )
        source = (ROOT / "scripts" / "publication_state.py").read_text(encoding="utf-8")
        literals = [
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        for forbidden in (
            "release upload",
            "release delete",
            "release edit",
            "release create",
            "release delete-asset",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertFalse(
                    [item for item in literals if forbidden in item],
                    f"a mutating GitHub CLI command is spelled out in the tool: {forbidden}",
                )
        with self.assertRaises(publication_state.GhInvocationError):
            publication_state.run_gh(
                ["gh", "release", "upload", "tag", "file.iso", "--repo", "o/r"]
            )


if __name__ == "__main__":
    unittest.main()
