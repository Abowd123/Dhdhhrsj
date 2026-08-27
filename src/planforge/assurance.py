"""
كتلة الاعتماد: على أي أرقام يستند هذا الحكم، وكم منها موقَّع.

هذا ما يحوّل «لم أتحقّق من الأرقام» من تحذير في نهاية تقرير إلى خاصية
مقيسة في كل مخرج، ومانعٍ للتسليم يُرفع بالتوقيع لا بعَلَم في سطر أوامر.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable
from planforge.codes.provenance import (
    REGISTRY, Confidence, SafetyDirection, values_of,
)
from planforge.codes.signing import (
    STATE_STALE, STATE_UNSIGNED, SignatureBook, default_profiles,
)
from planforge.codes.usage import dependencies_of
from planforge.rules.core import ComplianceReport, Severity

UNTRUSTED = frozenset({STATE_UNSIGNED, STATE_STALE})


@dataclass(frozen=True, slots=True)
class ValueAssurance:
    path: str
    state: str
    confidence: str
    reference: str
    current: str
    signed_by: str = ""
    signed_on: str = ""
    direction: str = ""

    @property
    def untrusted(self) -> bool:
        return self.state in UNTRUSTED


@dataclass
class Assurance:
    fingerprint: str
    relied_on: list[ValueAssurance] = field(default_factory=list)
    total_registry: int = 0

    @property
    def unsigned(self) -> list[ValueAssurance]:
        return [v for v in self.relied_on if v.untrusted]

    @property
    def permissive_unsigned(self) -> list[ValueAssurance]:
        """غير موقَّع + خطؤه يميل إلى التسامح = أعلى خطر."""
        return [
            v for v in self.unsigned
            if v.direction == SafetyDirection.PERMISSIVE
        ]

    @property
    def recalled_unsigned(self) -> list[ValueAssurance]:
        return [
            v for v in self.unsigned if v.confidence == Confidence.RECALLED
        ]

    @property
    def delivery_ready(self) -> bool:
        return not self.unsigned

    def stamp(self) -> str:
        if self.delivery_ready:
            return f"CODE VALUES SIGNED — assurance {self.fingerprint}"
        return (
            f"NOT FOR CONSTRUCTION — {len(self.unsigned)} unsigned code "
            f"values ({len(self.permissive_unsigned)} permissive) — "
            f"assurance {self.fingerprint}"
        )

    def summary_ar(self) -> str:
        if self.delivery_ready:
            return (
                f"كل الأرقام التي استند إليها هذا الحكم موقَّعة "
                f"({len(self.relied_on)} رقمًا). بصمة الاعتماد "
                f"{self.fingerprint}."
            )
        return (
            f"هذا الحكم يستند إلى {len(self.relied_on)} رقمًا، "
            f"{len(self.unsigned)} منها غير موقَّع "
            f"({len(self.permissive_unsigned)} خطؤها يميل إلى التسامح، "
            f"{len(self.recalled_unsigned)} كُتب من الذاكرة). "
            f"غير صالح للتسليم."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "delivery_ready": self.delivery_ready,
            "relied_on_count": len(self.relied_on),
            "unsigned_count": len(self.unsigned),
            "permissive_unsigned_count": len(self.permissive_unsigned),
            "recalled_unsigned_count": len(self.recalled_unsigned),
            "registry_total": self.total_registry,
            "stamp": self.stamp(),
            "summary_ar": self.summary_ar(),
            "values": [asdict(v) for v in self.relied_on],
        }


def assess(
    reports: Iterable[ComplianceReport],
    *,
    book: SignatureBook | None = None,
    profiles: dict[str, Any] | None = None,
    include_all_run_rules: bool = True,
) -> Assurance:
    """
    يبني كتلة الاعتماد من تقارير التدقيق.

    `include_all_run_rules=True` (الافتراضي) يحسب كل معرّف **فُحص**، لا
    ما وقع فقط. الحكم بأن المخطط مطابق يستند إلى الأرقام نفسها التي كان
    سيستند إليها لو خالف — وحصر الحساب على المخالفات يُخفي مخاطر الأحكام
    الإيجابية، وهي الأخطر لأنها ما يُسلَّم.
    """
    profiles = profiles or default_profiles()
    book = book or SignatureBook()
    values = values_of(profiles)

    codes: set[str] = set()
    for rep in reports:
        codes.update(
            v.rule_id for v in rep.violations
            if v.severity is not Severity.INFO
        )
        if include_all_run_rules:
            codes.update(rep.rules_run)

    paths: set[str] = set()
    for code in codes:
        paths |= dependencies_of(code)

    rows: list[ValueAssurance] = []
    for path in sorted(paths):
        prov = REGISTRY.get(path)
        value = values.get(path)
        st = book.status_of(path, value)
        rows.append(ValueAssurance(
            path=path,
            state=st.state,
            confidence=prov.confidence if prov else "unknown",
            reference=prov.ref.label() if prov and prov.ref else "—",
            current=repr(value),
            signed_by=st.signature.signed_by if st.signature else "",
            signed_on=st.signature.signed_on if st.signature else "",
            direction=prov.safety_direction if prov else "",
        ))

    return Assurance(
        fingerprint=book.fingerprint(profiles),
        relied_on=rows,
        total_registry=len(REGISTRY.paths()),
    )


def annotate(rep: ComplianceReport, book: SignatureBook) -> list[dict]:
    """
    لكل مخالفة: حالة الأرقام التي استندت إليها.

    يُكتب بجانب كل تقرير، فيرى المراجع أي مخالفة تقف على رقم موقَّع وأيها
    على رقم لم يقرأه أحد.
    """
    profiles = default_profiles()
    values = values_of(profiles)
    out: list[dict] = []
    for v in rep.violations:
        if v.severity is Severity.INFO:
            continue
        paths = sorted(dependencies_of(v.rule_id))
        states = {
            p: book.status_of(p, values.get(p)).state for p in paths
        }
        out.append({
            "rule": v.rule_id,
            "severity": v.severity,
            "message": v.message,
            "rests_on": states,
            "fully_signed": all(
                s not in UNTRUSTED for s in states.values()
            ),
        })
    return out
