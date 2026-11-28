# SPDX-License-Identifier: LicenseRef-Volnist
"""Repair known WSM release-tag inconsistencies without rewriting history."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


RESTORE_RELEASE_TAGS: dict[str, str] = {
    "0.1.0-rc3-minimal-live": "fb5d27a7aa0b156183fdee842acb06da9dcb64ca",
    "0.1.0-rc4-minimal-live": "e042fba5fd1faad5ccb2fb432183a80f4e0286ad",
    "0.1.0-rc5-minimal-live": "873cf9660a686f9ae28cf41045344aaab02b4b52",
}

OBSOLETE_TRIGGER_TAGS: dict[str, str] = {
    "packages-20261128-1": "75d5c8f128b79950abafea87d554cc49caf5a392",
    "packages-20261128-2": "e305848ea27699fdf1e5492b499b3cf98fc9d69b",
}


@dataclass(frozen=True)
class Action:
    kind: str
    tag: str
    sha: str
    reason: str


def refs_by_tag(refs: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for ref in refs:
        full_name = ref.get("ref", "")
        if not full_name.startswith("refs/tags/"):
            continue
        tag = full_name.removeprefix("refs/tags/")
        obj = ref.get("object")
        if not isinstance(obj, dict) or not isinstance(obj.get("sha"), str):
            raise ValueError(f"malformed Git ref: {full_name!r}")
        value = {"sha": obj["sha"], "type": str(obj.get("type", ""))}
        previous = result.get(tag)
        if previous is not None and previous != value:
            raise ValueError(f"GitHub returned conflicting refs for tag {tag!r}")
        result[tag] = value
    return result


def plan_reconciliation(
    refs: list[dict[str, Any]], releases: list[dict[str, Any]]
) -> list[Action]:
    """Return an exact, fail-closed plan; no API mutation occurs here."""
    tags = refs_by_tag(refs)
    releases_by_tag: dict[str, dict[str, Any]] = {}
    for release in releases:
        tag = release.get("tag_name")
        if not isinstance(tag, str):
            continue
        if tag in releases_by_tag:
            raise ValueError(f"multiple GitHub Releases reference tag {tag!r}")
        releases_by_tag[tag] = release

    unexpected_package_tags = sorted(
        tag
        for tag in tags
        if tag.startswith("packages-") and tag not in OBSOLETE_TRIGGER_TAGS
    )
    if unexpected_package_tags:
        raise ValueError(
            "unexpected packages-* tags require manual review: "
            + ", ".join(unexpected_package_tags)
        )

    actions: list[Action] = []

    for tag, expected_sha in RESTORE_RELEASE_TAGS.items():
        current = tags.get(tag)
        if current is not None:
            if current != {"sha": expected_sha, "type": "commit"}:
                raise ValueError(
                    f"refusing to move existing tag {tag!r}: "
                    f"expected lightweight commit {expected_sha}, got {current}"
                )
            continue

        release = releases_by_tag.get(tag)
        if release is None:
            raise ValueError(f"cannot restore {tag!r}: matching GitHub Release is missing")
        if release.get("target_commitish") != expected_sha:
            raise ValueError(
                f"cannot restore {tag!r}: Release target "
                f"{release.get('target_commitish')!r} != {expected_sha!r}"
            )
        if release.get("prerelease") is not True or release.get("draft") is not True:
            raise ValueError(
                f"cannot restore {tag!r}: expected an unpublished prerelease draft"
            )
        actions.append(
            Action(
                "create",
                tag,
                expected_sha,
                "restore the missing ref for its existing Minimal Live draft Release",
            )
        )

    for tag, expected_sha in OBSOLETE_TRIGGER_TAGS.items():
        if tag in releases_by_tag:
            raise ValueError(
                f"refusing to delete {tag!r}: a GitHub Release still references it"
            )
        current = tags.get(tag)
        if current is None:
            continue
        if current != {"sha": expected_sha, "type": "commit"}:
            raise ValueError(
                f"refusing to delete {tag!r}: expected lightweight commit "
                f"{expected_sha}, got {current}"
            )
        actions.append(
            Action(
                "delete",
                tag,
                expected_sha,
                "retire an obsolete package-workflow trigger with no Release",
            )
        )

    return actions


def run_gh_api(
    repo: str,
    method: str,
    endpoint: str,
    fields: dict[str, str] | None = None,
) -> Any:
    command = ["gh", "api", "--method", method, endpoint]
    for key, value in (fields or {}).items():
        command.extend(["-f", f"{key}={value}"])
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"gh api {method} {endpoint} failed "
            f"({completed.returncode}): {completed.stderr.strip()}"
        )
    if not completed.stdout.strip():
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub API returned invalid JSON for {endpoint}") from exc


def fetch_collection(repo: str, endpoint: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = run_gh_api(
            repo,
            "GET",
            f"{endpoint}?per_page=100&page={page}",
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"expected a JSON array from {endpoint}")
        items.extend(payload)
        if len(payload) < 100:
            return items
        page += 1


def reconcile(repo: str, apply: bool) -> list[Action]:
    refs_endpoint = f"repos/{repo}/git/matching-refs/tags/"
    releases_endpoint = f"repos/{repo}/releases"
    refs = fetch_collection(repo, refs_endpoint)
    releases = fetch_collection(repo, releases_endpoint)
    actions = plan_reconciliation(refs, releases)

    if not actions:
        print("Release tags are already reconciled; no mutation required.")
        return []

    for action in actions:
        print(
            f"{'APPLY' if apply else 'PLAN'} {action.kind.upper()} "
            f"refs/tags/{action.tag} -> {action.sha}: {action.reason}"
        )
        if not apply:
            continue
        if action.kind == "create":
            run_gh_api(
                repo,
                "POST",
                f"repos/{repo}/git/refs",
                {"ref": f"refs/tags/{action.tag}", "sha": action.sha},
            )
        elif action.kind == "delete":
            run_gh_api(repo, "DELETE", f"repos/{repo}/git/refs/tags/{action.tag}")
        else:
            raise AssertionError(f"unknown reconciliation action: {action.kind}")

    if not apply:
        print("Dry run only. Pass --apply from the protected main-branch workflow to mutate refs.")
        return actions

    updated_refs = fetch_collection(repo, refs_endpoint)
    updated_tags = refs_by_tag(updated_refs)
    for tag, expected_sha in RESTORE_RELEASE_TAGS.items():
        if updated_tags.get(tag) != {"sha": expected_sha, "type": "commit"}:
            raise RuntimeError(f"post-write verification failed for restored tag {tag!r}")
    for tag in OBSOLETE_TRIGGER_TAGS:
        if tag in updated_tags:
            raise RuntimeError(f"post-write verification failed: obsolete tag {tag!r} remains")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("## Release tag reconciliation\n\n")
            handle.write("| Operation | Tag | Commit |\n| --- | --- | --- |\n")
            for action in actions:
                handle.write(
                    f"| {action.kind} | `{action.tag}` | "
                    f"`{action.sha[:12]}` |\n"
                )
            handle.write(
                "\nVerified all restored refs and confirmed obsolete trigger refs are absent.\n"
            )
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="owner/repository; defaults to GITHUB_REPOSITORY",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the planned Git-ref changes (default: dry run)",
    )
    args = parser.parse_args()
    if not args.repo or "/" not in args.repo:
        parser.error("--repo or GITHUB_REPOSITORY must be owner/name")
    if args.apply and not os.environ.get("GH_TOKEN"):
        parser.error("--apply requires GH_TOKEN from a write-authorized workflow")
    try:
        reconcile(args.repo, args.apply)
    except (RuntimeError, ValueError) as exc:
        print(f"release-tag reconciliation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
