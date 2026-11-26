# SPDX-License-Identifier: LicenseRef-Volnist
"""Classify a machine as certified, known or unknown - per subsystem.

The installer never meets the same hardware twice, so "supported hardware" is
not a list. It is a judgement about *this* machine, made from evidence, and it
has three levels rather than two:

* **certified** - we have a valid evidence bundle for this machine and it says
  this function passed. Someone ran it and wrote down the result.
* **known** - the component was discovered and something drives it, but this
  exact combination has not been verified. It will probably work; nobody
  promised it.
* **unknown** - nothing was discovered, or nothing drives it. Not "broken":
  *not known*, which is a different statement and needs a different response.

The response is what matters:

* **stop** - a critical subsystem is unknown; continuing would produce a system
  that cannot boot, or one that destroys data on the way.
* **warn** - the system will install and boot, but something will not work, and
  the user has to agree to that.
* **proceed** - unknown peripherals are recorded and nothing else.

`unknown` never silently becomes `known`. That is the whole point of the third
level: without it, "we did not check" degrades into "we checked and it is fine".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

CERTIFIED = "certified"
KNOWN = "known"
UNKNOWN = "unknown"

STOP = "stop"
WARN = "warn"
PROCEED = "proceed"

# Which report categories form which subsystem. A subsystem is a unit of
# judgement: users care whether storage works, not which PCI address it sits on.
SUBSYSTEMS: dict[str, tuple[str, ...]] = {
    "cpu": ("cpu",),
    "memory": ("memory",),
    "firmware": ("motherboard",),
    "storage": ("storage-controller", "storage-device"),
    "graphics": ("gpu", "display"),
    "network": ("network",),
    "audio": ("audio",),
    "bluetooth": ("bluetooth",),
    "input": ("input",),
    "usb": ("usb-controller",),
    "camera": ("camera",),
    "other": ("other",),
}

# Unknown here means the machine may not boot or may lose data, so the installer
# stops rather than guesses.
CRITICAL = frozenset({"firmware", "storage", "cpu", "memory"})

# Unknown here is survivable: the system installs, boots, and something inside it
# does not work. The user must agree, because they may not find out until later.
DEGRADING = frozenset({"graphics", "network", "audio", "bluetooth", "input"})

# Everything else is recorded and nothing more.
PERIPHERAL = frozenset({"usb", "camera", "other"})


@dataclass
class SubsystemVerdict:
    subsystem: str
    level: str
    devices: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    assessed: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "level": self.level,
            "devices": list(self.devices),
            "reasons": list(self.reasons),
            "assessed": self.assessed,
        }


def _devices_for(report: dict[str, Any], categories: Iterable[str]) -> list[dict[str, Any]]:
    wanted = set(categories)
    return [device for device in report.get("devices", []) if device.get("category") in wanted]


def _evidence_cover(evidence: dict[str, Any] | None) -> dict[str, str]:
    """Map a verified function name to its status, from a profile evidence bundle."""
    if not evidence:
        return {}
    cover: dict[str, str] = {}
    for item in evidence.get("verified_functions", []) or []:
        name = str(item.get("name", "")).lower()
        status = str(item.get("status", "not-assessed"))
        if name:
            cover[name] = status
    return cover


def classify_subsystem(
    report: dict[str, Any],
    subsystem: str,
    evidence: dict[str, Any] | None = None,
) -> SubsystemVerdict:
    devices = _devices_for(report, SUBSYSTEMS.get(subsystem, ()))
    identifiers = [str(device.get("device_id", "?")) for device in devices]
    verdict = SubsystemVerdict(subsystem=subsystem, level=UNKNOWN, devices=identifiers)

    if not devices:
        # Absence in the report is not proof of absence on the machine: the
        # report may simply not cover this subsystem. The level stays unknown,
        # but the reason says which kind of unknown it is, because the two need
        # different sentences in front of a user.
        verdict.reasons.append("this report does not assess this subsystem")
        verdict.assessed = False
        return verdict

    # Certified requires evidence about *this* machine, not a driver that happens
    # to be loaded: someone has to have run the function and recorded the result.
    cover = _evidence_cover(evidence)
    if cover.get(subsystem) == "pass":
        verdict.level = CERTIFIED
        verdict.reasons.append("a verified evidence bundle records this function as passing")
        return verdict
    if cover.get(subsystem) in {"fail", "not-assessed"}:
        verdict.reasons.append(f"evidence exists but records this function as {cover[subsystem]}")

    discovered: list[str] = []
    undriven: list[str] = []
    for device in devices:
        status = str(device.get("discovery_status", "unknown"))
        driver = device.get("driver") or {}
        driver_name = str(driver.get("name") or driver.get("module") or "").strip()
        if status in {"unknown", "not-detected"}:
            undriven.append(f"{device.get('device_id', '?')}: discovery is {status}")
        elif not driver_name:
            undriven.append(f"{device.get('device_id', '?')}: discovered but no driver is bound")
        else:
            discovered.append(f"{device.get('device_id', '?')}: {driver_name}")

    if discovered and not undriven:
        verdict.level = KNOWN
        verdict.reasons.extend(discovered)
    else:
        verdict.level = UNKNOWN
        verdict.reasons.extend(undriven)
        verdict.reasons.extend(discovered)
    return verdict


def classify(
    report: dict[str, Any],
    evidence: dict[str, Any] | None = None,
    subsystems: Iterable[str] | None = None,
) -> dict[str, Any]:
    chosen = list(subsystems) if subsystems else list(SUBSYSTEMS)
    verdicts = [classify_subsystem(report, name, evidence) for name in chosen]

    decision = PROCEED
    for verdict in verdicts:
        if verdict.level != UNKNOWN:
            continue
        if verdict.subsystem in CRITICAL:
            decision = STOP
        elif verdict.subsystem in DEGRADING and decision != STOP:
            decision = WARN

    unknown_critical = [
        v.subsystem for v in verdicts if v.level == UNKNOWN and v.subsystem in CRITICAL
    ]
    unknown_degrading = [
        v.subsystem for v in verdicts if v.level == UNKNOWN and v.subsystem in DEGRADING
    ]
    not_assessed = [v.subsystem for v in verdicts if not v.assessed]

    return {
        "schema": "wsm-hardware-classification/1",
        "decision": decision,
        "counts": {
            CERTIFIED: sum(1 for v in verdicts if v.level == CERTIFIED),
            KNOWN: sum(1 for v in verdicts if v.level == KNOWN),
            UNKNOWN: sum(1 for v in verdicts if v.level == UNKNOWN),
        },
        "subsystems": [v.as_dict() for v in verdicts],
        "stop_because": unknown_critical,
        "warn_because": unknown_degrading,
        "not_assessed": not_assessed,
        "note": (
            "unknown is not a failure: it means this machine's behaviour was not "
            "verified here. A decision to stop is about consequences, not about "
            "how much we like the hardware."
        ),
    }


def explain(result: dict[str, Any]) -> str:
    """One short paragraph a person can act on."""
    decision = result["decision"]
    if decision == STOP:
        names = ", ".join(result["stop_because"])
        missing = [name for name in result["stop_because"] if name in result.get("not_assessed", [])]
        if missing and len(missing) == len(result["stop_because"]):
            return (
                f"Installation stopped: {names} was not assessed by this report. "
                "That is a gap in the report, not a verdict on the machine - "
                "run wsm-hwcheck on the target and use that report instead."
            )
        return (
            f"Installation stopped: {names} could not be identified or driven. "
            "Continuing could produce a system that does not boot. "
            "Send the hardware report so this machine can be classified properly."
        )
    if decision == WARN:
        names = ", ".join(result["warn_because"])
        return (
            f"Installation can continue, but {names} is unverified and may not work. "
            "The system will install and boot; agree explicitly before continuing."
        )
    return "Nothing critical is unknown. Unverified peripherals are recorded in the report."
