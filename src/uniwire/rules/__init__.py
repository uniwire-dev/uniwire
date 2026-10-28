"""Rules engine: domain checks beyond the JSON Schema, grouped into profiles.

Each rule receives the resolved document and its index and yields ``Finding`` objects.
The ``core`` profile always applies; the others are enabled through ``profiles``.
Finding messages are translated with :mod:`uniwire.i18n` (``UNIWIRE_LANG``, English by default).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from ..i18n import t as _t
from ..model import Document
from ..resolve import Index, build_index

Level = Literal["error", "warning", "info"]


@dataclass
class Finding:
    """Result of a rule: ``level`` (error / warning / info), stable ``rule`` name, translated ``message``,
    id of the ``node`` concerned and the ``source`` (reference) backing the rule."""

    level: Level
    rule: str
    message: str
    node: str | None = None
    source: str | None = None  # reference backing the rule

    def __str__(self) -> str:
        where = f" [{self.node}]" if self.node else ""
        return f"{self.level.upper():7} {self.rule}{where}: {self.message}"


Confidence = Literal["high", "medium"]


@dataclass(frozen=True)
class RuleInfo:
    """Rule metadata: stable name, source (reference) and confidence.

    ``high``: value stated in the cited source; ``medium``: interpretation or general principle.
    """

    name: str
    source: str
    confidence: Confidence

    def finding(self, level: Level, message: str, node: str | None = None) -> Finding:
        """A :class:`Finding` of this rule (name and source filled in)."""
        return Finding(level, self.name, message, node, self.source)


RULE_INFO: dict[str, RuleInfo] = {}


def describe(name: str, source: str, confidence: Confidence) -> RuleInfo:
    """Register the metadata of a rule in :data:`RULE_INFO` and return it."""
    info = RuleInfo(name, source, confidence)
    RULE_INFO[name] = info
    return info


Rule = Callable[[Document, Index], Iterable[Finding]]
PROFILES: dict[str, list[Rule]] = {"core": []}


def rule(profile: str) -> Callable[[Rule], Rule]:
    """Decorator registering a rule function ``(doc, index) -> findings`` in ``profile``."""
    def deco(fn: Rule) -> Rule:
        PROFILES.setdefault(profile, []).append(fn)
        return fn
    return deco


def check(doc: Document, profiles: Iterable[str] | None = None) -> list[Finding]:
    """Run the ``core`` rules and those of ``profiles`` (default: the document's ``profiles``).

    An unknown profile gives a warning finding. Returns the findings in rule order.
    """
    index = build_index(doc)
    active = ["core", *(profiles if profiles is not None else doc.profiles)]
    findings: list[Finding] = []
    for p in dict.fromkeys(active):
        if p not in PROFILES:
            findings.append(Finding("warning", "profile", _t("rules.unknown_profile", profile=p)))
            continue
        for r in PROFILES[p]:
            findings.extend(r(doc, index))
    if not any(p in PROFILES for p in active if p != "core"):
        findings.append(_no_profile(doc))
    elif any(p in CABLE_PROFILES for p in active) and not _any_cable_size(index):
        findings.append(Finding("info", "core.no-cables", _t("rules.no_cables")))  # 'no finding' is not 'cables OK'
    return findings


#: Profiles that check the cables against their protection.
CABLE_PROFILES = ("nfc15100", "vde0100", "iec60364")


def _any_cable_size(index: Index) -> bool:
    """A protected circuit with a cable size, or nothing protected (nothing to size)."""
    nodes = list(index.nodes.values())
    if not any(getattr(n, "in_A", None) and n.type in ("breaker", "rcbo", "fuse", "fuse_switch") for n in nodes):  # type: ignore[attr-defined]
        return True
    return any(c is not None and (c.section_mm2 or c.size_awg) for c in (getattr(n, "cable", None) for n in nodes))


#: Standards the rule profiles derive from.
COVERED_STANDARDS = ("NF C", "NFC", "IEC", "CEI", "60364", "VDE")


def _no_profile(doc: Document) -> Finding:
    """Only the core rules ran: say so, so that an empty result is not read as a checked installation."""
    std = (doc.installation.standard or "").strip()
    if std and not any(k in std.upper() for k in COVERED_STANDARDS):
        return Finding("info", "core.no-profile", _t("rules.standard_not_covered", standard=std))
    return Finding("info", "core.no-profile", _t("rules.no_profile"))


from . import core, enedis, iec60364, nfc15100, plc, vde0100  # noqa: E402,F401  (rule registration)
