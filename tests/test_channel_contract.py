# SPDX-License-Identifier: LicenseRef-Volnist
"""Lightweight source-tree contract for WSM's future Guix channel.

This is not Guix authentication or a proof of the effective Free dependency
closure. The repository currently keeps all WSM Scheme modules free of imports
from known nonfree namespaces as a conservative source-tree policy. The actual
channel remains the official Guix channel until the owner signs its introduction.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WSM = ROOT / "wsm"
CHANNELS = ROOT / "channels"
sys.path.insert(0, str(ROOT / "scripts"))

from check_channel_auth import main as channel_auth_main  # noqa: E402
from check_scheme_module_coverage import mask_scheme_non_code  # noqa: E402

DEFINE_MODULE = re.compile(r"\(define-module\s+\(([^)]+)\)")
NONFREE_MODULE = re.compile(
    r"\((?:nonguix|nongnu|linux-nonfree)(?:\s|\))|\bnvidia-driver\b",
    re.IGNORECASE,
)
INTRODUCTION_FORM = re.compile(r"\(introduction\b")


def modules_under(root: Path) -> dict[Path, list[str]]:
    """Return declared module names, masking comments/strings first.

    Duplicate names are an error, not a last-writer-wins dictionary update.
    The shared lexical masker is maintained by the module-coverage checker.
    """
    found: dict[Path, list[str]] = {}
    owners: dict[tuple[str, ...], Path] = {}
    for path in sorted(root.rglob("*.scm")):
        code = mask_scheme_non_code(path.read_text(encoding="utf-8"))
        match = DEFINE_MODULE.search(code)
        if match is None:
            continue
        name = tuple(match.group(1).split())
        previous = owners.get(name)
        if previous is not None:
            raise ValueError(
                f"duplicate Scheme module {name!r}: {previous} and {path}"
            )
        owners[name] = path
        found[path] = list(name)
    return found


def nonfree_module_imports(root: Path) -> dict[str, str]:
    """Find known nonfree module identifiers in executable Scheme source."""
    offenders: dict[str, str] = {}
    for path in sorted(root.rglob("*.scm")):
        code = mask_scheme_non_code(path.read_text(encoding="utf-8"))
        if NONFREE_MODULE.search(code):
            offenders[path.relative_to(root).as_posix()] = NONFREE_MODULE.pattern
    return offenders


class ChannelContractTests(unittest.TestCase):
    def test_every_wsm_module_is_in_the_wsm_namespace(self) -> None:
        outside = {
            path.relative_to(ROOT).as_posix(): name
            for path, name in modules_under(WSM).items()
            if not name or name[0] != "wsm"
        }
        self.assertEqual(outside, {}, f"modules outside the (wsm ...) namespace: {outside}")

    def test_wsm_source_tree_has_no_known_nonfree_module_imports(self) -> None:
        """A conservative repository-wide source policy, not a Free closure proof."""
        offenders = nonfree_module_imports(WSM)
        self.assertEqual(
            offenders,
            {},
            "known nonfree module imports in WSM Scheme source: " + ", ".join(offenders),
        )

    def test_any_declared_introduction_names_a_fingerprint(self) -> None:
        """A syntactic fingerprint field is necessary, but never proof of trust."""
        for path in sorted(CHANNELS.glob("*.scm")):
            code = mask_scheme_non_code(path.read_text(encoding="utf-8"))
            if INTRODUCTION_FORM.search(code):
                self.assertIn(
                    "openpgp-fingerprint",
                    code,
                    f"{path.name}: an introduction must name its signing fingerprint",
                )

    def test_authentication_reporter_keeps_authentication_unknown(self) -> None:
        """Only Guix's git authenticate can decide the signed channel chain."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = channel_auth_main([str(ROOT)])
        self.assertEqual(result, 0)
        self.assertIn("authenticated: unknown by design", output.getvalue())

    def test_the_channel_documentation_states_the_trust_model(self) -> None:
        text = (CHANNELS / "README.md").read_text(encoding="utf-8")
        for phrase in ("introduction", "автентиф", "lock"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text.lower())

    def test_the_scan_finds_real_modules(self) -> None:
        """If lexical masking breaks, tests must not pass vacuously."""
        self.assertGreaterEqual(len(modules_under(WSM)), 2)

    def test_comments_and_strings_cannot_fake_a_module_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "fake.scm").write_text(
                '; (define-module (wsm fake line))\n'
                '#| (define-module (wsm fake block)) |#\n'
                '(display "(define-module (wsm fake string))")\n',
                encoding="utf-8",
            )
            self.assertEqual(modules_under(root), {})

    def test_comments_and_strings_cannot_fake_a_nonfree_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "fake.scm"
            fake.write_text(
                '; (use-modules (nonguix packages nvidia))\n'
                '#| (use-modules (nongnu packages linux)) |#\n'
                '(display "(nvidia-driver)")\n',
                encoding="utf-8",
            )
            self.assertEqual(nonfree_module_imports(root), {})
            fake.write_text(
                '(use-modules (nonguix packages nvidia))\n',
                encoding="utf-8",
            )
            self.assertEqual(len(nonfree_module_imports(root)), 1)

    def test_duplicate_module_declarations_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one.scm").write_text("(define-module (wsm duplicate))\n")
            (root / "two.scm").write_text("(define-module (wsm duplicate))\n")
            with self.assertRaisesRegex(ValueError, "duplicate Scheme module"):
                modules_under(root)


if __name__ == "__main__":
    unittest.main()
