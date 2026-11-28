# SPDX-License-Identifier: LicenseRef-Volnist
"""The channel package version must follow the release it ships in.

The package said `0.1.0-rc3' while RELEASE-REQUEST.txt asked for rc6. Nobody
noticed, because nothing compared them. That matters for substitutes: a client
would download a cache entry labelled with a version the release never had, and
the two sources of truth would drift further with every release.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_tag() -> str:
    for line in (ROOT / "RELEASE-REQUEST.txt").read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            return text
    raise AssertionError("RELEASE-REQUEST.txt has no active tag")


def package_version() -> str:
    text = (ROOT / "wsm" / "packages" / "wsm.scm").read_text(encoding="utf-8")
    match = re.search(r'\(version "([^"]+)"\)', text)
    if match is None:
        raise AssertionError("wsm-tools has no version field")
    return match.group(1)


class PackageVersionTests(unittest.TestCase):
    def test_the_package_version_matches_the_requested_release(self) -> None:
        tag = release_tag()
        version = package_version()
        self.assertTrue(
            tag.startswith(version),
            f"package says {version}, release request asks for {tag}",
        )

    def test_the_version_is_not_a_placeholder(self) -> None:
        self.assertNotIn("0.0.0", package_version())


if __name__ == "__main__":
    unittest.main()
