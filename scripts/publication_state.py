#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-Volnist
"""Answer "what is published right now, and does it match the repository?".

The question used to be answered by clicking through the GitHub UI. This tool
answers it in one command, from a machine where ``gh`` is authenticated:

    python3 scripts/publication_state.py

It is strictly read-only. It calls exactly two GitHub CLI operations —
``gh release list`` and ``gh release view`` — and never uploads, publishes,
edits, deletes or creates anything. ``READ_ONLY_COMMANDS`` below is the whole
surface, and ``tests/test_verify_release_assets.py`` asserts nothing else is
reachable from this module.

What it reports, per release: the tag, whether it is a draft or published, every
asset with its size and whether a checksum is published for it, and any asset
the repository expects but the release lacks.

What it refuses to guess
------------------------
Three things genuinely cannot be seen from the release API, so they are
reported as ``unknown`` with the reason, never as absent:

1. **A draft.** Nothing is public, and the asset list of a draft may still be
   growing. A draft is therefore ``published: false`` and its asset
   completeness is ``unknown``, not "missing".
2. **A workflow artifact.** Build logs, attestation bundles and other Actions
   artifacts are not release assets. They are not enumerable from the release
   API and they expire (90 days by default). Their absence here is not
   evidence that they were never produced.
3. **A substitute cache served from GitHub Pages.** ``docs/SUBSTITUTES.md``
   says the ``.narinfo``, ``nix-cache-info`` and ``signing-key.pub`` are
   deployed to Pages, and the URL exists only in the Actions run report. No URL
   is recorded in the repository, so this tool cannot say whether that cache is
   served.

A fourth, smaller unknown: the *content* of a checksum manifest is a file in
the release, not metadata about it. Pass ``--checksums FILE`` with a downloaded
``SHA256SUMS`` to turn "unknown" into "listed" or "not-listed".

Testability
-----------
The GitHub CLI's JSON is an input, not an ambient fact. ``--releases-json`` and
``--release-json`` feed recorded ``gh`` output in place of the network, which is
how the tests run without a network or a token.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = "wsm-publication-state/1"
DEFAULT_REPO = "juv4uk/wsm-desktop"
DEFAULT_LIMIT = 10

# The complete GitHub CLI surface of this tool. Read-only by construction: a
# caller cannot ask for `gh release upload` because no code path builds it.
READ_ONLY_COMMANDS = ("release list", "release view")

LIST_FIELDS = "tagName,name,isDraft,isPrerelease,publishedAt,createdAt"
VIEW_FIELDS = (
    "tagName,name,isDraft,isPrerelease,publishedAt,createdAt,"
    "targetCommitish,url,assets"
)

SUM_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")
DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
PART = re.compile(r"^(?P<iso>.+\.iso)\.part(?P<number>[0-9]{3})$")
WHOLE_IMAGE = re.compile(r"^.+\.iso$")

# Asset sets the repository's own tooling expects in a published release.
# `MINIMAL_LIVE_REQUIRED` is the same tuple `prepare_release_attestation_subjects`
# refuses to attest without; the supporting files are the ones
# `.github/workflows/release-minimal-live.yml` uploads and
# `scripts/check_release_readiness.py` requires in the bundle.
MINIMAL_LIVE_REQUIRED = (
    "SHA256SUMS",
    "build-manifest.json",
    "release-manifest.json",
    "boot-bios.json",
    "boot-uefi.json",
)
MINIMAL_LIVE_SUPPORTING = (
    "build.log",
    "channels.resolved.scm",
    "channel-resolution.log",
)
CACHE_REQUIRED = (
    "SHA256SUMS",
    "signing-key.pub",
    "provenance.json",
    "metadata.SHA256SUMS",
)
CACHE_NAR = re.compile(r"^.+\.nar\.zst$")

CHECKSUM_MANIFESTS = frozenset(
    {"SHA256SUMS", "ISO-CHECKSUMS.sha256", "metadata.SHA256SUMS", "provenance.SHA256SUMS"}
)
CHECKSUM_SIDECAR = "ISO-CHECKSUMS.sha256"

FAMILY_MINIMAL_LIVE = "minimal-live"
FAMILY_SUBSTITUTE_CACHE = "substitute-cache"
FAMILY_UNKNOWN = "unknown"


class PublicationStateError(ValueError):
    """The input does not describe a release this tool can report on."""


class GhInvocationError(PublicationStateError):
    """The GitHub CLI could not be run, or failed."""


def unknown(what: str, why: str, kind: str = "unresolved") -> dict[str, str]:
    """One thing this report cannot see.

    ``kind="unresolved"`` means the answer to "does this match the repository?"
    depends on it. ``kind="limitation"`` means the tool can never see it, so it
    is stated once and does not make every run's verdict inconclusive.
    """
    return {"what": what, "why": why, "kind": kind}


# --------------------------------------------------------------------------
# Reading gh's JSON
# --------------------------------------------------------------------------


def _object(payload: Any, source: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PublicationStateError(
            f"{source}: expected a JSON object, got {type(payload).__name__}"
        )
    return payload


def _text(payload: dict[str, Any], key: str, source: str, required: bool = True) -> str | None:
    value = payload.get(key)
    if value is None:
        if required:
            raise PublicationStateError(f"{source}: missing required field {key!r}")
        return None
    if not isinstance(value, str):
        raise PublicationStateError(
            f"{source}: field {key!r} must be a string, got {type(value).__name__}"
        )
    return value


def _flag(payload: dict[str, Any], key: str, source: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise PublicationStateError(
            f"{source}: field {key!r} must be true or false, got {value!r}"
        )
    return value


def parse_release_list(payload: Any, source: str) -> list[dict[str, Any]]:
    """Validate the output of `gh release list --json ...`."""
    if not isinstance(payload, list):
        raise PublicationStateError(
            f"{source}: expected a JSON array of releases, got {type(payload).__name__}"
        )
    releases: list[dict[str, Any]] = []
    for index, entry in enumerate(payload):
        label = f"{source}[{index}]"
        item = _object(entry, label)
        releases.append(
            {
                "tag": _text(item, "tagName", label),
                "name": _text(item, "name", label, required=False) or "",
                "is_draft": _flag(item, "isDraft", label),
                "is_prerelease": _flag(item, "isPrerelease", label),
                "published_at": _text(item, "publishedAt", label, required=False),
                "created_at": _text(item, "createdAt", label, required=False),
            }
        )
    return releases


def parse_asset(entry: Any, source: str) -> dict[str, Any]:
    item = _object(entry, source)
    name = _text(item, "name", source)
    if not name:
        raise PublicationStateError(f"{source}: asset name is empty")
    size = item.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise PublicationStateError(
            f"{source}: asset {name!r} has no usable integer 'size' (got {size!r})"
        )
    digest = item.get("digest")
    sha256 = None
    if isinstance(digest, str):
        match = DIGEST.match(digest)
        if match is not None:
            sha256 = match.group(1)
    return {
        "name": name,
        "size": size,
        "state": item.get("state") if isinstance(item.get("state"), str) else None,
        "github_sha256": sha256,
    }


def parse_release_detail(payload: Any, source: str) -> dict[str, Any]:
    """Validate the output of `gh release view <tag> --json ...`."""
    item = _object(payload, source)
    assets_payload = item.get("assets")
    if not isinstance(assets_payload, list):
        raise PublicationStateError(
            f"{source}: field 'assets' must be a JSON array, got "
            f"{type(assets_payload).__name__}"
        )
    assets = [
        parse_asset(entry, f"{source}.assets[{index}]")
        for index, entry in enumerate(assets_payload)
    ]
    names = [asset["name"] for asset in assets]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise PublicationStateError(
            f"{source}: duplicate asset names in one release: {', '.join(duplicates)}"
        )
    return {
        "tag": _text(item, "tagName", source),
        "name": _text(item, "name", source, required=False) or "",
        "is_draft": _flag(item, "isDraft", source),
        "is_prerelease": _flag(item, "isPrerelease", source),
        "published_at": _text(item, "publishedAt", source, required=False),
        "created_at": _text(item, "createdAt", source, required=False),
        "target_commitish": _text(item, "targetCommitish", source, required=False),
        "url": _text(item, "url", source, required=False),
        "assets": assets,
    }


def load_json_file(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PublicationStateError(f"{path}: cannot read: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PublicationStateError(
            f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})"
        ) from exc


def parse_checksums(path: Path) -> dict[str, str]:
    """Parse a downloaded sha256sum manifest into name -> digest."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PublicationStateError(f"{path}: cannot read checksums: {exc}") from exc
    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        match = SUM_LINE.fullmatch(line)
        if match is None:
            raise PublicationStateError(f"{path}: invalid sha256sum line {number}")
        digest, name = match.groups()
        entries[name] = digest.lower()
    if not entries:
        raise PublicationStateError(f"{path}: checksum manifest lists no files")
    return entries


# --------------------------------------------------------------------------
# Talking to the GitHub CLI (the only networked part)
# --------------------------------------------------------------------------


def run_gh(argv: Sequence[str]) -> str:
    """Run one read-only `gh` command and return its stdout."""
    command = " ".join(argv[1:3]) if len(argv) >= 3 else ""
    if command not in READ_ONLY_COMMANDS:
        raise GhInvocationError(
            f"refusing to run a non-read-only GitHub CLI command: {' '.join(argv)!r}"
        )
    try:
        result = subprocess.run(
            list(argv), capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise GhInvocationError(f"cannot run gh: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        reason = detail[-1] if detail else f"exit status {result.returncode}"
        raise GhInvocationError(f"gh {' '.join(argv[1:])} failed: {reason}")
    return result.stdout


def gh_release_list(repo: str, limit: int) -> list[dict[str, Any]]:
    argv = [
        "gh", "release", "list",
        "--repo", repo,
        "--limit", str(limit),
        "--json", LIST_FIELDS,
    ]
    return parse_release_list(load_json_text(run_gh(argv), "gh release list"), "gh release list")


def gh_release_view(repo: str, tag: str) -> dict[str, Any]:
    argv = [
        "gh", "release", "view", tag,
        "--repo", repo,
        "--json", VIEW_FIELDS,
    ]
    return parse_release_detail(
        load_json_text(run_gh(argv), f"gh release view {tag}"), f"gh release view {tag}"
    )


def load_json_text(text: str, source: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PublicationStateError(
            f"{source}: response is not valid JSON ({exc.msg} at line {exc.lineno})"
        ) from exc


# --------------------------------------------------------------------------
# Repository expectations
# --------------------------------------------------------------------------


def release_family(tag: str) -> str:
    if tag.endswith("-minimal-live"):
        return FAMILY_MINIMAL_LIVE
    if tag.startswith("h170-free-cache-"):
        return FAMILY_SUBSTITUTE_CACHE
    return FAMILY_UNKNOWN


def repository_request(root: Path) -> str | None:
    """The tag RELEASE-REQUEST.txt asks for, if the file names exactly one."""
    path = root / "RELEASE-REQUEST.txt"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    tags = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    return tags[0] if len(tags) == 1 else None


def repository_iso_names(root: Path) -> list[str]:
    """ISO names the repository's own checksum list claims are published."""
    path = root / "ISO-CHECKSUMS.sha256"
    try:
        entries = parse_checksums(path)
    except PublicationStateError:
        return []
    return sorted(entries)


def image_form(names: Iterable[str]) -> tuple[str, list[str]]:
    """Which image representation the release uses: whole, parts, both or neither."""
    names = list(names)
    whole = [name for name in names if WHOLE_IMAGE.match(name) and not PART.match(name)]
    parts = [name for name in names if PART.match(name)]
    if whole and parts:
        return "conflict", whole + parts
    if whole:
        return "whole", whole
    if parts:
        return "parts", parts
    return "missing", []


def evaluate_release(
    release: dict[str, Any],
    checksums: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compare one release against what the repository expects of its family."""
    tag = release["tag"]
    family = release_family(tag)
    names = [asset["name"] for asset in release["assets"]]
    present = set(names)

    report: dict[str, Any] = {
        "tag": tag,
        "name": release.get("name", ""),
        "family": family,
        "state": "draft" if release["is_draft"] else "published",
        "published": not release["is_draft"],
        "is_prerelease": release.get("is_prerelease", False),
        "published_at": release.get("published_at"),
        "created_at": release.get("created_at"),
        "target_commitish": release.get("target_commitish"),
        "url": release.get("url"),
        "asset_count": len(names),
        "assets": [],
        "missing_required": [],
        "missing_supporting": [],
        "extras": [],
        "problems": [],
        "unknowns": [],
    }

    for asset in release["assets"]:
        name = asset["name"]
        if name in CHECKSUM_MANIFESTS or name.startswith("SHA256SUMS") or name.endswith(".sha256"):
            status = "manifest"
        elif checksums is None:
            status = "unknown"
        elif name in checksums:
            status = "listed"
        else:
            status = "not-listed"
        entry = {
            "name": name,
            "size": asset["size"],
            "checksum": status,
            "github_sha256": asset.get("github_sha256"),
        }
        if status == "listed" and entry["github_sha256"]:
            entry["checksum_matches_github_digest"] = (
                checksums[name] == entry["github_sha256"]
            )
        report["assets"].append(entry)

    # A draft is not published, and its asset list may still be growing: an
    # incomplete-looking draft is "unknown", not "missing".
    if release["is_draft"]:
        report["unknowns"].append(
            unknown(
                f"asset completeness of draft {tag}",
                "a draft is not public and may still be receiving uploads; the "
                "listing below is a snapshot, so a missing asset is not evidence "
                "that it will never appear",
            )
        )
        report["unknowns"].append(
            unknown(
                f"publication of draft {tag}",
                "drafts are visible only to users with write access; nothing "
                "about this release is published yet",
            )
        )
        report["missing_required"] = sorted(
            name for name in _expected_required(family) if name not in present
        )
        report["missing_supporting"] = sorted(
            name for name in _expected_supporting(family) if name not in present
        )
        report["extras"] = sorted(present - _expected_names(family, names))
        report["unknowns"].extend(_family_unknowns(family))
        return report

    required = _expected_required(family)
    supporting = _expected_supporting(family)
    report["expected_required"] = list(required)
    report["expected_supporting"] = list(supporting)
    report["missing_required"] = sorted(name for name in required if name not in present)
    report["missing_supporting"] = sorted(name for name in supporting if name not in present)
    report["extras"] = (
        [] if family == FAMILY_UNKNOWN else sorted(present - _expected_names(family, names))
    )
    report["unknowns"].extend(_family_unknowns(family))

    if family == FAMILY_UNKNOWN:
        report["unknowns"].append(
            unknown(
                f"expected asset set for {tag}",
                "no publication rule in scripts/publication_state.py covers this "
                "tag family, so this report cannot say what the release should contain",
            )
        )
        return report

    if family == FAMILY_MINIMAL_LIVE:
        form, image_names = image_form(names)
        report["image_form"] = form
        if form == "missing":
            report["problems"].append(
                f"{tag}: no image asset — expected a whole *.iso or *.iso.partNNN set"
            )
        elif form == "conflict":
            report["problems"].append(
                f"{tag}: whole image and split parts are both published: "
                f"{', '.join(image_names)}"
            )
        elif form == "parts":
            if CHECKSUM_SIDECAR not in present:
                report["missing_required"].append(CHECKSUM_SIDECAR)
            report["unknowns"].append(
                unknown(
                    f"expected number of ISO parts for {tag}",
                    "the part count is recorded inside release-manifest.json, which "
                    "is an asset of this release; this tool does not download it, "
                    "so a short part list cannot be told apart from a complete one",
                    kind="limitation",
                )
            )
        elif CHECKSUM_SIDECAR in present:
            report["unknowns"].append(
                unknown(
                    f"why {CHECKSUM_SIDECAR} accompanies a whole image in {tag}",
                    "the workflow writes that sidecar only when the image is split; "
                    "its presence here is reported, not judged",
                    kind="limitation",
                )
            )

    if family == FAMILY_SUBSTITUTE_CACHE:
        nars = sorted(name for name in names if CACHE_NAR.match(name))
        report["nar_assets"] = len(nars)
        if not nars:
            report["problems"].append(
                f"{tag}: no *.nar.zst asset — a substitute cache release without NARs serves nothing"
            )
        report["unknowns"].append(
            unknown(
                f"expected number of NARs in {tag}",
                "the count follows the built store outputs recorded in provenance.json, "
                "which is an asset of this release and is not downloaded here",
                kind="limitation",
            )
        )
        report["unknowns"].append(
            unknown(
                "substitute cache served from GitHub Pages",
                "docs/SUBSTITUTES.md deploys .narinfo, nix-cache-info and "
                "signing-key.pub to Pages, and the URL exists only in the Actions "
                "run report; no Pages URL is recorded in the repository, so this "
                "tool cannot say whether the cache is being served",
            )
        )

    for name in report["missing_required"]:
        report["problems"].append(f"{tag}: expected asset is missing from the release: {name}")

    if checksums is None and any(
        asset["checksum"] == "unknown" for asset in report["assets"]
    ):
        report["unknowns"].append(
            unknown(
                "whether a checksum is published for each asset",
                "a checksum manifest is an asset, not metadata; pass "
                "--checksums FILE with a downloaded SHA256SUMS to resolve this",
            )
        )

    return report


def _expected_required(family: str) -> tuple[str, ...]:
    if family == FAMILY_MINIMAL_LIVE:
        return MINIMAL_LIVE_REQUIRED
    if family == FAMILY_SUBSTITUTE_CACHE:
        return CACHE_REQUIRED
    return ()


def _expected_supporting(family: str) -> tuple[str, ...]:
    if family == FAMILY_MINIMAL_LIVE:
        return MINIMAL_LIVE_SUPPORTING
    return ()


def _expected_all(family: str) -> set[str]:
    return set(_expected_required(family)) | set(_expected_supporting(family))


def _expected_names(family: str, names: Iterable[str]) -> set[str]:
    """Expected assets for one release, including its image representation.

    The image filename carries the version, so it cannot live in a constant:
    for a minimal-live release any *.iso, any *.iso.partNNN and the split
    sidecar are expected shapes. Whether the right *one* is present is decided
    by `image_form`, not here.
    """
    expected = _expected_all(family)
    if family == FAMILY_MINIMAL_LIVE:
        expected |= {name for name in names if WHOLE_IMAGE.match(name) or PART.match(name)}
        expected.add(CHECKSUM_SIDECAR)
    return expected


def _family_unknowns(family: str) -> list[dict[str, str]]:
    unknowns = [
        unknown(
            "workflow artifacts for this release (build logs, attestation bundles)",
            "Actions artifacts are not release assets, are not enumerable from the "
            "release API, and expire (90 days by default); they are not reported "
            "as missing because this tool cannot see them at all",
            kind="limitation",
        )
    ]
    return unknowns


# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------


def build_report(
    releases: list[dict[str, Any]],
    requested_tag: str | None = None,
    checksums: dict[str, str] | None = None,
    repository: str = DEFAULT_REPO,
    iso_names: Sequence[str] = (),
    detail_errors: dict[str, str] | None = None,
    single_tag: bool = False,
) -> dict[str, Any]:
    detail_errors = detail_errors or {}
    evaluated = [evaluate_release(release, checksums) for release in releases]

    problems: list[str] = []
    for release in evaluated:
        problems.extend(release["problems"])

    unknowns: list[dict[str, str]] = []
    for tag, reason in sorted(detail_errors.items()):
        # A release this run could not read is unknown, not a defect: the
        # release may be perfectly complete and simply unreachable (draft
        # without write access, rate limit, missing offline recording).
        unknowns.append(
            {
                "tag": tag,
                "what": f"publication state of {tag}",
                "why": f"release details could not be read: {reason}",
                "kind": "unresolved",
            }
        )
    for release in evaluated:
        for item in release["unknowns"]:
            unknowns.append({"tag": release["tag"], **item})

    requested: dict[str, Any] | None = None
    if requested_tag is not None:
        status = "absent-from-examined-releases"
        for release in evaluated:
            if release["tag"] == requested_tag:
                status = release["state"]
                break
        if status == "absent-from-examined-releases" and requested_tag in detail_errors:
            status = "unreadable"
        requested = {"tag": requested_tag, "status": status}

    iso_report = None
    if iso_names and not single_tag:
        entries = []
        for name in iso_names:
            holders = [
                release["tag"]
                for release in evaluated
                if any(
                    asset["name"] == name or asset["name"].startswith(name + ".part")
                    for asset in release["assets"]
                )
            ]
            entries.append(
                {
                    "name": name,
                    "status": f"present in {', '.join(holders)}" if holders else "unknown",
                    "releases": holders,
                }
            )
        iso_report = {"source": "ISO-CHECKSUMS.sha256", "entries": entries}
        for entry in entries:
            if single_tag:
                break
            if not entry["releases"]:
                unknowns.append(
                    {
                        "tag": None,
                        "what": f"publication of {entry['name']}",
                        "why": "ISO-CHECKSUMS.sha256 expects this image, but no asset "
                        "with that name appears in the examined releases; it may be "
                        "older than --limit, renamed, or never published",
                    }
                )

    unresolved = [item for item in unknowns if item.get("kind") != "limitation"]
    if problems:
        verdict = "mismatch"
    elif not evaluated:
        verdict = "unknown"
    elif unresolved:
        verdict = "match-with-unknowns"
    else:
        verdict = "match"

    return {
        "schema": SCHEMA,
        "repository": repository,
        "read_only": True,
        "gh_commands_used": list(READ_ONLY_COMMANDS),
        "requested_tag": requested,
        "releases": evaluated,
        "iso_checksum_list": iso_report,
        "unknowns": unknowns,
        "problems": problems,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PiB"


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"Publication state — {report['repository']}")
    add(
        "Read-only: produced with `gh release list` and `gh release view` only; "
        "nothing was uploaded, published, edited or deleted."
    )
    add("")
    requested = report.get("requested_tag")
    if requested:
        add(
            f"RELEASE-REQUEST.txt asks for {requested['tag']}: {requested['status']}"
        )
    published = [r for r in report["releases"] if r["published"]]
    if published:
        latest = published[0]
        when = latest.get("published_at") or "unknown time"
        add(f"Latest published release: {latest['tag']} ({when})")
    elif report["releases"]:
        add("No published release among the releases examined.")
    else:
        add("No release could be examined; see the unknown entries below.")
    add("")

    for release in report["releases"]:
        add(f"Release {release['tag']}")
        label = "pre-release" if release["is_prerelease"] else "release"
        if release["published"]:
            add(f"  state           : published {label}")
        else:
            add(f"  state           : DRAFT — not published {label}")
        if release.get("name"):
            add(f"  title           : {release['name']}")
        if release.get("published_at"):
            add(f"  published at    : {release['published_at']}")
        if release.get("target_commitish"):
            add(f"  target commit   : {release['target_commitish']}")
        add(f"  expected set    : {release['family']}")
        add(f"  assets ({release['asset_count']}):")
        width = max((len(asset["name"]) for asset in release["assets"]), default=4)
        width = max(width, 4)
        add(f"    {'NAME'.ljust(width)}  {'SIZE':>10}  CHECKSUM")
        for asset in release["assets"]:
            checksum = asset["checksum"]
            if checksum == "unknown":
                checksum = "unknown (manifest not read)"
            if checksum == "listed" and asset.get("checksum_matches_github_digest") is False:
                checksum = "listed (MISMATCH vs GitHub digest)"
            add(f"    {asset['name'].ljust(width)}  {human_size(asset['size']):>10}  {checksum}")
        if release.get("image_form"):
            add(f"  image form      : {release['image_form']}")
        if release["missing_required"]:
            add(f"  missing (required): {', '.join(release['missing_required'])}")
        else:
            add("  missing (required): none")
        if release["missing_supporting"]:
            add(f"  missing (supporting): {', '.join(release['missing_supporting'])}")
        add(
            "  extra assets    : "
            + (", ".join(release["extras"]) if release["extras"] else "none")
            + ("" if not release["extras"] else "  (reported, not fatal)")
        )
        if release["unknowns"]:
            add("  unknown:")
            for item in release["unknowns"]:
                add(f"    - [{item.get('kind', 'unresolved')}] {item['what']}")
                add(f"      why: {item['why']}")
        add("")

    iso = report.get("iso_checksum_list")
    if iso:
        add(f"Repository ISO list ({iso['source']}):")
        for entry in iso["entries"]:
            add(f"  {entry['name']}: {entry['status']}")
        add("")

    add(f"Verdict: {report['verdict']}")
    for problem in report["problems"]:
        add(f"  problem: {problem}")
    examined = {release["tag"] for release in report["releases"]}
    unattached = [
        item for item in report["unknowns"] if item.get("tag") not in examined
    ]
    if unattached:
        add("Unknown, repository-wide:")
        for item in unattached:
            add(f"  - [{item.get('kind', 'unresolved')}] {item['what']}")
            add(f"    why: {item['why']}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publication-state",
        description=(
            "Report what is published for a repository right now and whether it "
            "matches what the repository expects. Read-only."
        ),
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="OWNER/REPO to inspect")
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"how many recent releases to examine (default {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--tag", action="append", default=None,
        help="examine only this tag (repeatable); default is the newest --limit releases",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--checksums", type=Path, default=None,
        help="downloaded SHA256SUMS, used to say whether each asset has a published checksum",
    )
    parser.add_argument(
        "--releases-json", type=Path, default=None,
        help="offline: recorded output of `gh release list --json ...`",
    )
    parser.add_argument(
        "--release-json", type=Path, action="append", default=None,
        help="offline: recorded output of `gh release view <tag> --json ...` (repeatable)",
    )
    parser.add_argument(
        "--root", type=Path, default=ROOT,
        help="repository root used to read RELEASE-REQUEST.txt and ISO-CHECKSUMS.sha256",
    )
    parser.add_argument(
        "--fail-on-mismatch", action="store_true",
        help="exit 1 when a published release lacks an asset the repository expects",
    )
    return parser


def collect_offline(
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    assert args.releases_json is not None
    listing = parse_release_list(load_json_file(args.releases_json), str(args.releases_json))
    details: dict[str, dict[str, Any]] = {}
    for path in args.release_json or []:
        detail = parse_release_detail(load_json_file(path), str(path))
        details[detail["tag"]] = detail
    errors: dict[str, str] = {}
    selected = []
    wanted = args.tag or [entry["tag"] for entry in listing]
    for tag in wanted:
        if tag in details:
            selected.append(details[tag])
        else:
            errors[tag] = (
                "offline mode has no --release-json for this tag; recorded "
                "`gh release view` output is required to report its assets"
            )
    return selected, details, errors


def collect_online(
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    listing = gh_release_list(args.repo, args.limit)
    tags = args.tag or [entry["tag"] for entry in listing]
    selected: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for tag in tags:
        try:
            selected.append(gh_release_view(args.repo, tag))
        except PublicationStateError as exc:
            errors[tag] = str(exc)
    return selected, errors


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1:
        print("publication-state: --limit must be at least 1", file=sys.stderr)
        return 2
    try:
        checksums = parse_checksums(args.checksums) if args.checksums else None
        if args.releases_json is not None:
            releases, _, errors = collect_offline(args)
        else:
            releases, errors = collect_online(args)
        report = build_report(
            releases,
            requested_tag=repository_request(args.root),
            checksums=checksums,
            repository=args.repo,
            iso_names=repository_iso_names(args.root),
            detail_errors=errors,
            single_tag=bool(args.tag),
        )
    except PublicationStateError as exc:
        print(f"publication-state: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_text(report))
    if args.fail_on_mismatch and report["verdict"] == "mismatch":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
