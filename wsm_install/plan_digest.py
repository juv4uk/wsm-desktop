# SPDX-License-Identifier: LicenseRef-Volnist
"""A canonical digest for an install plan, so consent and journals can bind to it.

#280 acceptance criterion 1 asks for an immutable/typed plan with a canonical
digest, and criterion 4 asks that each destructive step's consent be bound to the
exact command it authorises. Both need the same primitive: a value that changes if
anything in the plan changes and cannot be shifted by reordering fields.

The serialization is not reinvented here: `wsm_install.plan.canonical_json` already
defines what "canonical" means in this repository, and the backend pins its own
plan with it. Using the same function is the point — a second canonicalizer would
be a second truth.

What this does NOT do: it does not make the plan immutable (Python lists stay
mutable), and it is not a signature. It is the binding target a consent record and
a journal entry can quote; proving who approved it is a separate concern, and
treating a hash as proof of authorship would repeat the mistake the ADR provenance
gate exists to catch.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

from wsm_install.install_steps import Step
from wsm_install.plan import canonical_json

SCHEMA = "wsm-install-plan/1"


class PlanDigestError(Exception):
    """A plan that cannot be digested, with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _render_step(step: Step, index: int) -> dict[str, object]:
    if not isinstance(step, Step):
        raise PlanDigestError("plan.step-type", f"step {index} is not a Step")
    if not step.command:
        raise PlanDigestError("plan.command", f"step {index} has an empty argv")
    if not all(isinstance(argument, str) for argument in step.command):
        raise PlanDigestError("plan.command", f"step {index} has a non-string argv element")
    return {
        "argv": list(step.command),
        "destructive": bool(step.destructive),
        "purpose": step.purpose,
    }


def canonical_plan(disk: str, steps: Sequence[Step]) -> dict[str, object]:
    """Return the canonical document the digest is taken over."""
    if not isinstance(disk, str) or not disk:
        raise PlanDigestError("plan.disk", "the plan needs a target disk string")
    if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise PlanDigestError("plan.steps", "steps must be a sequence of Step values")
    if not steps:
        raise PlanDigestError("plan.empty", "a plan with no steps has nothing to bind to")

    return {
        "disk": disk,
        "schema": SCHEMA,
        "steps": [_render_step(step, index) for index, step in enumerate(steps, start=1)],
    }


def _digest(document: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def plan_digest(disk: str, steps: Sequence[Step]) -> str:
    """SHA-256 over the canonical plan document, as lowercase hex."""
    return _digest(canonical_plan(disk, steps))


def step_digest(disk: str, step: Step, index: int) -> str:
    """Digest binding one step to the plan it belongs to and to its position.

    Consent for a destructive step quotes this value: the same argv at a different
    index, or against a different disk, is a different authorisation.
    """
    if not isinstance(index, int) or index < 1:
        raise PlanDigestError("plan.index", "step index must be a positive integer")
    return _digest(
        {
            "disk": disk,
            "index": index,
            "schema": SCHEMA,
            "step": _render_step(step, index),
        }
    )
