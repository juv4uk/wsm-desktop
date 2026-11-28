# SPDX-License-Identifier: LicenseRef-Volnist
"""The release-tag repair plan must be exact and fail closed."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reconcile_release_tags.py"
SPEC = importlib.util.spec_from_file_location("reconcile_release_tags", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

RESTORE = MODULE.RESTORE_RELEASE_TAGS
OBSOLETE = MODULE.OBSOLETE_TRIGGER_TAGS


def make_ref(tag: str, sha: str, kind: str = "commit") -> dict:
    return {"ref": f"refs/tags/{tag}", "object": {"sha": sha, "type": kind}}


def make_release(tag: str, sha: str, *, draft: bool = True) -> dict:
    return {
        "tag_name": tag,
        "target_commitish": sha,
        "draft": draft,
        "prerelease": True,
    }


class ReleaseTagReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.refs = [
            make_ref(tag, sha) for tag, sha in OBSOLETE.items()
        ] + [
            make_ref("0.1.0-rc1", "325505fcc9cb4d3a0ed17e2f09d0ff7f3ff93536"),
            make_ref("0.1.0-rc2-live-iso", "b6d082f4437766c033af73dfde8ac0326c3ff044"),
            make_ref("0.1.0-rc6-minimal-live", "1fa19879ec780e372cce9a6bb4c13f613d01ec9f"),
        ]
        self.releases = [
            make_release(tag, sha) for tag, sha in RESTORE.items()
        ]

    def test_repairs_only_the_three_orphaned_minimal_live_refs(self) -> None:
        actions = MODULE.plan_reconciliation(self.refs, self.releases)
        created = {(item.tag, item.sha) for item in actions if item.kind == "create"}
        self.assertEqual(created, set(RESTORE.items()))

    def test_removes_only_the_two_known_unreleased_package_triggers(self) -> None:
        actions = MODULE.plan_reconciliation(self.refs, self.releases)
        deleted = {(item.tag, item.sha) for item in actions if item.kind == "delete"}
        self.assertEqual(deleted, set(OBSOLETE.items()))

    def test_does_not_touch_existing_product_or_withdrawn_tags(self) -> None:
        refs = self.refs + [
            make_ref(
                "wsm-tools-0.1.0-rc6-a7501a36c33c-run-46119662030",
                "a7501a36c33cf3cc7d0ae0f44301d77822c00f77",
            ),
            make_ref(
                "wsm-channel-d4903a89b4e8",
                "d4903a89b4e856258b037fa27e7e61464f9087ad",
            ),
        ]
        actions = MODULE.plan_reconciliation(refs, self.releases)
        touched = {item.tag for item in actions}
        self.assertNotIn("0.1.0-rc1", touched)
        self.assertNotIn("0.1.0-rc2-live-iso", touched)
        self.assertNotIn("0.1.0-rc6-minimal-live", touched)
        self.assertNotIn("wsm-tools-0.1.0-rc6-a7501a36c33c-run-46119662030", touched)
        self.assertNotIn("wsm-channel-d4903a89b4e8", touched)

    def test_existing_release_tag_is_never_moved(self) -> None:
        tag, expected_sha = next(iter(RESTORE.items()))
        refs = self.refs + [make_ref(tag, "0" * 40)]
        with self.assertRaisesRegex(ValueError, "refusing to move existing tag"):
            MODULE.plan_reconciliation(refs, self.releases)

    def test_missing_tag_requires_matching_release(self) -> None:
        with self.assertRaisesRegex(ValueError, "GitHub Release is missing"):
            MODULE.plan_reconciliation(self.refs, self.releases[1:])

    def test_release_target_must_match_the_pinned_commit(self) -> None:
        tag = next(iter(RESTORE))
        releases = [
            make_release(tag, "1" * 40),
            *self.releases[1:],
        ]
        with self.assertRaisesRegex(ValueError, "Release target"):
            MODULE.plan_reconciliation(self.refs, releases)

    def test_only_unpublished_prerelease_drafts_may_be_repaired(self) -> None:
        tag = next(iter(RESTORE))
        releases = [
            make_release(tag, RESTORE[tag], draft=False),
            *self.releases[1:],
        ]
        with self.assertRaisesRegex(ValueError, "unpublished prerelease draft"):
            MODULE.plan_reconciliation(self.refs, releases)

    def test_package_trigger_must_not_have_a_release(self) -> None:
        releases = [
            *self.releases,
            make_release(next(iter(OBSOLETE)), next(iter(OBSOLETE.values()))),
        ]
        with self.assertRaisesRegex(ValueError, "Release still references"):
            MODULE.plan_reconciliation(self.refs, releases)

    def test_package_trigger_sha_must_match_before_deletion(self) -> None:
        tag = next(iter(OBSOLETE))
        refs = [ref for ref in self.refs if ref["ref"] != f"refs/tags/{tag}"]
        refs.append(make_ref(tag, "2" * 40))
        with self.assertRaisesRegex(ValueError, "refusing to delete"):
            MODULE.plan_reconciliation(refs, self.releases)

    def test_unknown_packages_namespace_tag_requires_manual_review(self) -> None:
        refs = self.refs + [make_ref("packages-new-experiment", "3" * 40)]
        with self.assertRaisesRegex(ValueError, "unexpected packages"):
            MODULE.plan_reconciliation(refs, self.releases)

    def test_all_actions_are_idempotent_after_success(self) -> None:
        repaired_refs = [
            ref for ref in self.refs
            if ref["ref"].split("refs/tags/", 1)[1] not in OBSOLETE
        ]
        repaired_refs.extend(make_ref(tag, sha) for tag, sha in RESTORE.items())
        self.assertEqual(MODULE.plan_reconciliation(repaired_refs, self.releases), [])


if __name__ == "__main__":
    unittest.main()
