# SPDX-License-Identifier: GPL-3.0-or-later
"""Guix deployment adapter: turn a confirmed install plan into a typed handoff.

This module implements the backend side of docs/INSTALLER-HANDOFF.md for the
selected backend (GNU Guix, see ADR 0004). It is deliberately split from any
installer frontend: nothing here imports Calamares or reads a user interface.

The adapter never executes anything. ``prepare`` returns an immutable handoff
that carries the generated configuration text and an allow-listed argv list;
running that argv is the caller's decision, and only after the caller has
revalidated the target. That keeps the "no target mutation before
BACKEND_APPLY" rule checkable rather than aspirational.

Every value that reaches the generated Scheme is validated against an
allow-list first. User text never becomes a shell command, and never becomes
Scheme syntax.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .plan import canonical_json

BACKEND_ID = "guix-system"
ADAPTER_VERSION = "0.1.0"

# Allow-lists. Anything that does not match is refused, not escaped and hoped
# for: a wrong hostname is a cheap failure, an injected form is not.
DEVICE_PATTERN = re.compile(r"/dev/[a-zA-Z0-9][a-zA-Z0-9._-]*")
HOSTNAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
ACCOUNT_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,16}$")
LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}_[A-Z]{2}\.[A-Za-z0-9-]+$")
TIMEZONE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+)*$")
KEYBOARD_PATTERN = re.compile(r"^[a-z]{2}(-[a-z0-9]+)?$")

# argv is built from these two words only. The Guix deployment command is the
# single allowed entry point for the Guix backend; NixOS commands are never
# reachable from this module.
GUIX_PROGRAM = "guix"
GUIX_SUBCOMMAND = ("system", "init")
GUIX_CONFIGURATION_PATH = "/run/wsm/system.scm"
GUIX_TARGET_MOUNTPOINT = "/mnt"


class HandoffError(Exception):
    """A refusal. Carries a stable code so callers can map it to UI text."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TargetSelection:
    """Everything the user must choose explicitly before a plan is confirmable."""

    disk: str
    hostname: str
    timezone: str
    locale: str
    keyboard_layout: str
    username: str
    full_name: str
    root_label: str
    efi_label: str
    boot_mode: str  # "efi" or "bios"

    def digest(self) -> str:
        """Stable digest of the selection, used to detect post-confirmation edits."""
        # Hash a canonical JSON array, not a delimiter-joined string: user
        # text such as a full name may itself contain the delimiter.
        material = canonical_json([
            self.disk,
            self.hostname,
            self.timezone,
            self.locale,
            self.keyboard_layout,
            self.username,
            self.full_name,
            self.root_label,
            self.efi_label,
            self.boot_mode,
        ])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GuixHandoff:
    """The result of a successful prepare step. No side effects have happened."""

    backend_id: str
    adapter_version: str
    configuration: str
    configuration_sha256: str
    argv: tuple[str, ...]
    target_digest: str
    plan_sha256: str

    def describe(self) -> str:
        return (
            f"backend={self.backend_id} adapter={self.adapter_version} "
            f"config_sha256={self.configuration_sha256[:12]} "
            f"target={self.target_digest[:12]} plan={self.plan_sha256[:12]}"
        )


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise HandoffError(code, message)


def validate_plan(plan: dict[str, Any]) -> None:
    """Refuse any plan that is not a confirmed, Guix-only, blocker-free plan."""
    _require(
        isinstance(plan, dict) and plan.get("plan_version") == "0.1.0",
        "plan.version",
        "unsupported plan version; expected 0.1.0",
    )
    backend = plan.get("backend") or {}
    _require(
        backend.get("id") == BACKEND_ID,
        "plan.backend",
        f"this adapter only deploys {BACKEND_ID}, got {backend.get('id')!r}; "
        "one installation has exactly one backend",
    )
    _require(
        not plan.get("blockers"),
        "plan.blockers",
        f"plan has unresolved blockers: {plan.get('blockers')}",
    )
    readiness = plan.get("plan_readiness") or {}
    _require(
        readiness.get("confirmable") is True,
        "plan.not_confirmable",
        "plan is diagnostic-only; required user selections are still missing: "
        f"{readiness.get('required_user_actions')}",
    )
    _require(
        not readiness.get("missing_required_roles"),
        "plan.missing_roles",
        f"required device roles were never observed: {readiness.get('missing_required_roles')}",
    )
    execution = plan.get("execution") or {}
    _require(
        execution.get("dry_run") is True,
        "plan.dry_run",
        "plan was not produced in dry-run mode",
    )
    _require(
        execution.get("disk_access_performed") is False,
        "plan.disk_access",
        "plan already claims disk access; refusing to continue",
    )
    _require(
        bool(plan.get("plan_sha256")),
        "plan.hash",
        "plan carries no plan_sha256; it cannot be confirmed",
    )
    expected_plan_sha256 = hashlib.sha256(
        canonical_json({key: value for key, value in plan.items() if key != "plan_sha256"}).encode("utf-8")
    ).hexdigest()
    _require(
        plan["plan_sha256"] == expected_plan_sha256,
        "plan.digest_mismatch",
        "plan contents do not match plan_sha256; refusing stale or modified plan data",
    )
    source = plan.get("source_report") or {}
    _require(
        bool(source.get("sha256")) and bool(source.get("report_id")),
        "plan.provenance",
        "plan does not reference the report it was derived from",
    )


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    """Use full-string matching; `re.match` plus `$` accepts a final newline."""
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def validate_selection(selection: TargetSelection) -> None:
    """Refuse any selection value that is not in its allow-list."""
    _require(
        _matches(DEVICE_PATTERN, selection.disk),
        "selection.disk",
        f"target disk {selection.disk!r} is not a plain /dev path",
    )
    _require(
        _matches(HOSTNAME_PATTERN, selection.hostname),
        "selection.hostname",
        f"hostname {selection.hostname!r} is not a valid hostname",
    )
    _require(
        _matches(ACCOUNT_PATTERN, selection.username),
        "selection.username",
        f"username {selection.username!r} is not a valid account name",
    )
    _require(
        _matches(LABEL_PATTERN, selection.root_label)
        and _matches(LABEL_PATTERN, selection.efi_label),
        "selection.label",
        "filesystem labels must be 1-16 characters of letters, digits, dot, dash or underscore",
    )
    _require(
        selection.root_label != selection.efi_label,
        "selection.label_collision",
        "root and EFI filesystem labels must differ",
    )
    _require(
        _matches(LOCALE_PATTERN, selection.locale),
        "selection.locale",
        f"locale {selection.locale!r} is not a valid locale name",
    )
    _require(
        _matches(TIMEZONE_PATTERN, selection.timezone)
        and all(part not in {".", ".."} for part in selection.timezone.split("/")),
        "selection.timezone",
        f"timezone {selection.timezone!r} is not a valid timezone name",
    )
    _require(
        _matches(KEYBOARD_PATTERN, selection.keyboard_layout),
        "selection.keyboard_layout",
        f"keyboard layout {selection.keyboard_layout!r} is not a valid layout name",
    )
    _require(
        selection.boot_mode in {"efi", "bios"},
        "selection.boot_mode",
        f"boot mode {selection.boot_mode!r} must be 'efi' or 'bios'",
    )
    _require(
        isinstance(selection.full_name, str)
        and len(selection.full_name) <= 80
        and not any(
            unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
            for character in selection.full_name
        ),
        "selection.full_name",
        "full name must be a single line of at most 80 characters without control or format characters",
    )


def _scheme_string(value: str) -> str:
    """Quote an already-validated value for Scheme.

    Validation is the security boundary; this function only prevents a value
    from breaking the generated file's syntax.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_configuration(plan: dict[str, Any], selection: TargetSelection) -> str:
    """Render the Guix operating-system declaration for this target.

    The generated configuration owns file systems, user accounts, services and
    the bootloader. The installer frontend must not run a second bootloader
    job against the same target.
    """
    if selection.boot_mode == "efi":
        bootloader = (
            "  (bootloader (bootloader-configuration\n"
            "                (bootloader grub-efi-bootloader)\n"
            "                (targets (list \"/boot/efi\"))))\n"
        )
        extra_file_system = (
            "    (file-system\n"
            "     (mount-point \"/boot/efi\")\n"
            f"     (device (file-system-label {_scheme_string(selection.efi_label)}))\n"
            "     (type \"vfat\"))\n"
        )
    else:
        bootloader = (
            "  (bootloader (bootloader-configuration\n"
            "                (bootloader grub-bootloader)\n"
            f"                (targets (list {_scheme_string(selection.disk)}))))\n"
        )
        extra_file_system = ""

    source = plan["source_report"]
    return (
        ";; Generated by the WSM Guix deployment adapter. Do not edit by hand.\n"
        f";; adapter={ADAPTER_VERSION} plan_sha256={plan['plan_sha256']}\n"
        f";; report_id={source['report_id']} report_sha256={source['sha256']}\n"
        "\n"
        "(use-modules (gnu))\n"
        "(use-service-modules networking ssh)\n"
        "\n"
        "(operating-system\n"
        f"  (host-name {_scheme_string(selection.hostname)})\n"
        f"  (timezone {_scheme_string(selection.timezone)})\n"
        f"  (locale {_scheme_string(selection.locale)})\n"
        f"  (keyboard-layout (keyboard-layout {_scheme_string(selection.keyboard_layout)}))\n"
        "\n"
        f"{bootloader}"
        "\n"
        "  (file-systems\n"
        "   (cons*\n"
        "    (file-system\n"
        "     (mount-point \"/\")\n"
        f"     (device (file-system-label {_scheme_string(selection.root_label)}))\n"
        "     (type \"ext4\"))\n"
        f"{extra_file_system}"
        "    %base-file-systems))\n"
        "\n"
        "  (users\n"
        "   (cons* (user-account\n"
        f"           (name {_scheme_string(selection.username)})\n"
        f"           (comment {_scheme_string(selection.full_name)})\n"
        "           (group \"users\")\n"
        "           (supplementary-groups '(\"wheel\" \"netdev\" \"audio\" \"video\"))\n"
        f"           (home-directory {_scheme_string('/home/' + selection.username)}))\n"
        "          %base-user-accounts))\n"
        "\n"
        "  (services\n"
        "   (cons* (service openssh-service-type)\n"
        "          %base-services)))\n"
    )


def build_argv(configuration_path: str, target_mountpoint: str) -> tuple[str, ...]:
    """Return the deployment argv as a typed list, never a shell string.

    ``guix system init`` is the only deployment command this adapter can
    produce. The caller runs it, and only after revalidating the target.
    """
    _require(
        configuration_path == GUIX_CONFIGURATION_PATH,
        "argv.config_path",
        f"configuration path must be the installer-owned path {GUIX_CONFIGURATION_PATH!r}",
    )
    _require(
        target_mountpoint == GUIX_TARGET_MOUNTPOINT,
        "argv.mountpoint",
        f"target mountpoint must be the installer-owned mount root {GUIX_TARGET_MOUNTPOINT!r}",
    )
    return (GUIX_PROGRAM, *GUIX_SUBCOMMAND, configuration_path, target_mountpoint)


def prepare(
    plan: dict[str, Any],
    selection: TargetSelection,
    *,
    confirmed_plan_sha256: str,
    confirmed_target_digest: str,
    external_bootloader_job: bool = False,
    configuration_path: str = "/run/wsm/system.scm",
    target_mountpoint: str = "/mnt",
) -> GuixHandoff:
    """Validate everything and return the handoff. Nothing is executed or written."""
    _require(
        not external_bootloader_job,
        "handoff.bootloader_owner",
        "the generated configuration owns the bootloader; a second bootloader job "
        "would give one system two owners",
    )
    validate_plan(plan)
    validate_selection(selection)

    _require(
        confirmed_plan_sha256 == plan["plan_sha256"],
        "handoff.plan_changed",
        "the plan changed after confirmation; the confirmation is void",
    )
    _require(
        confirmed_target_digest == selection.digest(),
        "handoff.target_changed",
        "the target selection changed after confirmation; the confirmation is void",
    )

    configuration = render_configuration(plan, selection)
    return GuixHandoff(
        backend_id=BACKEND_ID,
        adapter_version=ADAPTER_VERSION,
        configuration=configuration,
        configuration_sha256=hashlib.sha256(configuration.encode("utf-8")).hexdigest(),
        argv=build_argv(configuration_path, target_mountpoint),
        target_digest=selection.digest(),
        plan_sha256=plan["plan_sha256"],
    )
