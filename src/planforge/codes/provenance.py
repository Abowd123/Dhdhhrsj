"""
سجل إثبات الأرقام: لكل قيمة في ملفات الكود مسار، وفقرة مُدّعاة، وحالة.

الفلسفة: الكود لا يستطيع التحقّق من رقم ضد نص قانوني — لكنه يستطيع أن
يضمن ثلاثة أشياء، وهي ما يفعله هذا الملف:
  • ألا يوجد رقم بلا سجل: `coverage()` تكشف الفجوة، واختبار يُفشل البناء.
  • أن يبطل التوقيع عند تغيّر القيمة: `value_digest()` أساس القفل.
  • أن يُعرف لكل حكمٍ على أي أرقام استند: `usage.py` يبني الشجرة.

المراجعة نفسها عمل المهندس لا عمل هذا الملف.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any, Iterator


class Confidence(StrEnum):
    """
    كيف وصل الرقم إلى الملف. لا تُغني عن التوقيع، لكنها تُرتّب المراجعة.
    """
    QUOTED = "quoted"          # نُقل عن نص مباشرة (يبقى بحاجة تصديق)
    DERIVED = "derived"        # مشتق بحساب من أرقام منصوصة
    RECALLED = "recalled"      # من الذاكرة — الأخطر، وأول ما يُراجع
    CONVENTION = "convention"  # عرف مهني لا نص قانوني
    ENGINE = "engine"          # معامل محرك لا علاقة له بالكود


class SafetyDirection(StrEnum):
    """
    لو كان الرقم خاطئًا، فإلى أين يميل الخطأ؟

    `PERMISSIVE` أخطر تصنيف في المشروع: خطؤه **يُمرّر** مخالفة بدل أن
    يوقفها. رقمٌ متحفّظ خاطئ يرفض مخططًا صالحًا فيُكتشف؛ ورقمٌ متسامح
    خاطئ يُجيز مخططًا مخالفًا فيُسلَّم.
    """
    CONSERVATIVE = "conservative"
    PERMISSIVE = "permissive"
    EXACT = "exact"


@dataclass(frozen=True, slots=True)
class CodeRef:
    """
    الفقرة المُدّعاة — تُنسب ولا تُصدَّق.

    `document` و`clause` إلزاميان لكل رقم كودي. العرف المهني يحمل مرجعًا
    صريحًا بأنه عرف، فلا تُنسب سلطةُ فقرةٍ إلى ما لا نصّ له.
    """
    document: str
    edition: str
    clause: str
    page: str = ""
    url: str = ""

    @property
    def is_statutory(self) -> bool:
        return not self.document.startswith("عرف")

    def label(self) -> str:
        bits = [self.document, self.edition, self.clause]
        if self.page:
            bits.append(f"ص {self.page}")
        return " — ".join(b for b in bits if b and b != "—")


CONVENTION_REF = CodeRef("عرف مهني (لا نص قانوني)", "—", "—")


@dataclass(frozen=True, slots=True)
class Provenance:
    path: str                 # "uk.bedroom_min_width[bedroom_double]"
    unit: str                 # "mm" | "mm2" | "deg" | "ratio" | "-"
    confidence: Confidence
    ref: CodeRef | None       # None فقط لمعاملات المحرك
    note: str = ""
    safety_direction: SafetyDirection = SafetyDirection.EXACT

    @property
    def needs_signature(self) -> bool:
        return self.confidence is not Confidence.ENGINE

    @property
    def is_high_risk(self) -> bool:
        """غير منصوص + خطؤه متسامح = ابدأ المراجعة من هنا."""
        return (
            self.confidence is Confidence.RECALLED
            and self.safety_direction is SafetyDirection.PERMISSIVE
        )


class Registry:
    def __init__(self) -> None:
        self._items: dict[str, Provenance] = {}

    def add(self, p: Provenance) -> Provenance:
        if p.path in self._items:
            raise ValueError(f"سجل إثبات مكرر: {p.path}")
        if p.needs_signature and p.ref is None:
            raise ValueError(f"{p.path}: رقم كودي بلا مرجع فقرة")
        self._items[p.path] = p
        return p

    def get(self, path: str) -> Provenance | None:
        return self._items.get(path)

    def paths(self) -> frozenset[str]:
        return frozenset(self._items)

    def signable(self) -> frozenset[str]:
        return frozenset(
            p for p, v in self._items.items() if v.needs_signature
        )

    def by_confidence(self, c: Confidence) -> list[Provenance]:
        return sorted(
            (v for v in self._items.values() if v.confidence is c),
            key=lambda v: v.path,
        )

    def by_document(self, needle: str) -> list[Provenance]:
        low = needle.lower()
        return sorted(
            (
                v for v in self._items.values()
                if v.ref and low in v.ref.document.lower()
            ),
            key=lambda v: v.path,
        )

    def high_risk(self) -> list[Provenance]:
        return sorted(
            (v for v in self._items.values() if v.is_high_risk),
            key=lambda v: v.path,
        )

    def all(self) -> list[Provenance]:
        return sorted(self._items.values(), key=lambda v: v.path)


REGISTRY = Registry()


# ═══════════════ تعداد القيم الفعلية ═══════════════

_LEAF_TYPES = (bool, int, float)
_SKIP_TYPES = (str, frozenset, set, bytes)
"""
`str` و`frozenset` تصنيفات لا مقاسات: مجموعة أنواع الغرف التي ينطبق
عليها خلوص الدوران قرارُ نطاقٍ لا رقمٌ يُوقَّع. أما `bool` فورقة صريحة:
`hob_under_window_forbidden` قرار سلامة يُراجع ويُوقَّع.
"""


def enumerate_values(obj: Any, prefix: str) -> Iterator[tuple[str, Any]]:
    """
    يمشي على حقول dataclass ويُخرج (المسار، القيمة) لكل ورقة.

    القواميس تتوسّع بمفاتيحها، والمتتاليات الرقمية تُعَدّ ورقة واحدة
    (`stair_2r_plus_g` مجالٌ يُوقَّع كوحدة لا طرفَين).
    """
    if not is_dataclass(obj):
        raise TypeError(f"{prefix}: ليس dataclass")
    for f in fields(obj):
        yield from _walk(f"{prefix}.{f.name}", getattr(obj, f.name))


def _walk(path: str, value: Any) -> Iterator[tuple[str, Any]]:
    # الترتيب مقصود: bool فرعٌ من int، فيُفحص أولًا كي لا يُفلت
    if isinstance(value, bool):
        yield (path, value)
        return
    if isinstance(value, _SKIP_TYPES):
        return
    if isinstance(value, _LEAF_TYPES):
        yield (path, value)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            key = k.value if isinstance(k, StrEnum) else str(k)
            yield from _walk(f"{path}[{key}]", v)
        return
    if isinstance(value, (tuple, list)):
        if value and all(isinstance(v, _LEAF_TYPES) for v in value):
            yield (path, tuple(value))
            return
        for i, v in enumerate(value):
            yield from _walk(f"{path}[{i}]", v)
        return
    if is_dataclass(value):
        yield from enumerate_values(value, path)


def values_of(profiles: dict[str, Any]) -> dict[str, Any]:
    """
    خريطة {المسار: القيمة} لكل ملفات الكود.

    تُبنى مرة وتُمرَّر: النداء المفرد على `_value_at` كان يُعيد التعداد
    كاملًا لكل مسار، فصار حساب كتلة اعتماد بأربعين مسارًا أربعين تعدادًا.
    """
    out: dict[str, Any] = {}
    for prefix, obj in profiles.items():
        out.update(enumerate_values(obj, prefix))
    return out


def value_digest(value: Any) -> str:
    """تلبيد قيمة بشكل قانوني — أساس قفل التوقيع."""
    payload = json.dumps(
        list(value) if isinstance(value, tuple) else value,
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class CoverageGap:
    path: str
    reason: str


def coverage(profiles: dict[str, Any]) -> tuple[list[CoverageGap], int]:
    """
    يقارن القيم الفعلية بسجل الإثبات.

    أي فجوة عيبٌ برمجي لا دَين مراجعة: رقمٌ بلا سجل يتسلّل إلى الأحكام
    بلا مسار للتوقيع، وسجلٌّ بلا رقم يطلب توقيع ما لا وجود له. الاختبار
    يفشل، و`codes audit` يخرج بالرمز 2.
    """
    values = values_of(profiles)
    gaps = [
        CoverageGap(p, "قيمة بلا سجل إثبات")
        for p in sorted(values)
        if REGISTRY.get(p) is None
    ]
    gaps += [
        CoverageGap(p, "سجل إثبات لقيمة غير موجودة")
        for p in sorted(REGISTRY.paths() - set(values))
        if (prov := REGISTRY.get(p)) is not None and prov.needs_signature
    ]
    return gaps, len(values)
