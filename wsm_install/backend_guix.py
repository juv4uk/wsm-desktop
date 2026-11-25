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
REPORT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,80}")
REPORT_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
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
        return hashlib.sha256(material.encode("utf-8", "backslashreplace")).hexdigest()


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
    backend = plan.get("backend")
    _require(
        isinstance(backend, dict),
        "plan.backend_shape",
        "backend must be an object",
    )
    _require(
        backend.get("id") == BACKEND_ID,
        "plan.backend",
        f"this adapter only deploys {BACKEND_ID}, got {backend.get('id')!r}; "
        "one installation has exactly one backend",
    )
    blockers = plan.get("blockers")
    _require(
        isinstance(blockers, list),
        "plan.blockers_shape",
        "blockers must be an array",
    )
    _require(
        not blockers,
        "plan.blockers",
        f"plan has unresolved blockers: {blockers}",
    )
    readiness = plan.get("plan_readiness")
    _require(
        isinstance(readiness, dict),
        "plan.readiness_shape",
        "plan_readiness must be an object",
    )
    _require(
        readiness.get("confirmable") is True,
        "plan.not_confirmable",
        "plan is diagnostic-only; required user selections are still missing: "
        f"{readiness.get('required_user_actions')}",
    )
    _require(
        plan.get("plan_mode") == "dry-run",
        "plan.mode",
        "Guix handoff accepts only a dry-run plan snapshot",
    )
    _require(
        plan.get("plan_status") == "confirmation-ready",
        "plan.not_confirmation_ready",
        "only a confirmation-ready plan can enter the Guix handoff; diagnostic-only plans are never accepted",
    )
    missing_roles = readiness.get("missing_required_roles")
    _require(
        isinstance(missing_roles, list),
        "plan.missing_roles_shape",
        "plan_readiness.missing_required_roles must be an array",
    )
    _require(
        not missing_roles,
        "plan.missing_roles",
        f"required device roles were never observed: {missing_roles}",
    )
    required_actions = readiness.get("required_user_actions")
    _require(
        isinstance(required_actions, list),
        "plan.user_actions_shape",
        "plan_readiness.required_user_actions must be an array",
    )
    _require(
        not required_actions,
        "plan.user_actions",
        f"required user actions remain unresolved: {required_actions}",
    )
    execution = plan.get("execution")
    _require(
        isinstance(execution, dict),
        "plan.execution_shape",
        "execution must be an object",
    )
    _require(
        execution.get("dry_run") is True,
        "plan.dry_run",
        "plan was not produced in dry-run mode",
    )
    _require(
        execution.get("plan_confirmable") is True,
        "plan.execution_not_confirmable",
        "execution.plan_confirmable must agree with plan_readiness.confirmable",
    )
    _require(
        execution.get("mutations_authorized") is False,
        "plan.mutations_authorized",
        "prepare-only handoff must not carry mutation authorization",
    )
    _require(
        execution.get("backend_invoked") is False,
        "plan.backend_invoked",
        "plan already claims backend execution; refusing to continue",
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
    source_value = plan.get("source_report")
    _require(
        isinstance(source_value, dict),
        "plan.provenance",
        "source_report must be an object containing report identity and digest",
    )
    source = source_value if isinstance(source_value, dict) else {}
    _require(
        _matches(REPORT_ID_PATTERN, source.get("report_id")),
        "plan.report_id",
        "source_report.report_id must be 16-80 ASCII letters, digits, underscore or dash",
    )
    _require(
        _matches(REPORT_SHA256_PATTERN, source.get("sha256")),
        "plan.report_sha256",
        "source_report.sha256 must be exactly 64 lowercase hexadecimal characters",
    )


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    """Require a full-string match; never accept trailing data or newlines."""
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