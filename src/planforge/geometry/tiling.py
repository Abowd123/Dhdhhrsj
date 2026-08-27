"""
مقاطع الحدود في تبليط: الوحدة الذرّية المشتركة بين الجدران والفتحات.

`drawing/walls.py` يبني منها الجدران بسماكاتها، و`solver/refine.py` يبني
منها الأبواب والنوافذ. كانت الدالة مكرَّرة في الملفين، ونسختان من منطق
هندسي واحد تتباعدان: تُصلح إحداهما ويبقى العيب في الأخرى.

المقطع يعرف أي غرفتين يفصل — وهذا وحده ما يجعله كافيًا لحمل فتحة.
"""
from __future__ import annotations
from dataclasses import dataclass
from planforge.codes.uk.detail_profile import DETAIL
from planforge.enums import Axis
from planforge.geometry.rect import Rect
from planforge.units import TOL


@dataclass(frozen=True, slots=True)
class Segment:
    axis: Axis
    coord: int          # x إن رأسي، y إن أفقي
    lo: int
    hi: int
    a: str | None       # الغرفة على الجهة الدنيا (يسار/أسفل)، None = الخارج
    b: str | None       # الغرفة على الجهة العليا (يمين/أعلى)، None = الخارج

    @property
    def length(self) -> int:
        return self.hi - self.lo

    @property
    def is_external(self) -> bool:
        return self.a is None or self.b is None

    def rooms(self) -> tuple[str, ...]:
        return tuple(x for x in (self.a, self.b) if x)

    def room_set(self) -> frozenset[str]:
        return frozenset(self.rooms())


def _accessors(axis: Axis, env: Rect):
    """(بداية الحد، نهايته، بداية المدى، نهايته، طرفا المظروف)."""
    if axis is Axis.V:
        return (
            (lambda r: r.x), (lambda r: r.x2),
            (lambda r: r.y), (lambda r: r.y2),
            env.x, env.x2,
        )
    return (
        (lambda r: r.y), (lambda r: r.y2),
        (lambda r: r.x), (lambda r: r.x2),
        env.y, env.y2,
    )


def segments_on_axis(
    rects: dict[str, Rect], env: Rect, axis: Axis
) -> list[Segment]:
    """كل مقاطع الحدود على محور واحد، مرتَّبة ترتيبًا قانونيًا."""
    k_lo, k_hi, s_lo, s_hi, e_lo, e_hi = _accessors(axis, env)
    coords = sorted(
        {k_lo(r) for r in rects.values()} | {k_hi(r) for r in rects.values()}
    )
    out: list[Segment] = []

    for c in coords:
        before = sorted(
            ((i, r) for i, r in rects.items() if abs(k_hi(r) - c) <= TOL),
            key=lambda kv: s_lo(kv[1]),
        )
        after = sorted(
            ((i, r) for i, r in rects.items() if abs(k_lo(r) - c) <= TOL),
            key=lambda kv: s_lo(kv[1]),
        )

        if abs(c - e_lo) <= TOL:
            out += [
                Segment(axis, c, s_lo(r), s_hi(r), None, i) for i, r in after
            ]
            continue
        if abs(c - e_hi) <= TOL:
            out += [
                Segment(axis, c, s_lo(r), s_hi(r), i, None) for i, r in before
            ]
            continue

        for ia, ra in before:
            for ib, rb in after:
                lo = max(s_lo(ra), s_lo(rb))
                hi = min(s_hi(ra), s_hi(rb))
                if hi - lo > TOL:
                    out.append(Segment(axis, c, lo, hi, ia, ib))
    return out


def boundary_segments(rects: dict[str, Rect], env: Rect) -> list[Segment]:
    """كل مقاطع الحدود: بين غرفتين، أو بين غرفة والخارج."""
    return (
        segments_on_axis(rects, env, Axis.V)
        + segments_on_axis(rects, env, Axis.H)
    )


TILING_TOL_RATIO = DETAIL.tiling_tol_ratio
"""
سماحية نسبية على مجموع المساحات. مطلقٌ بالمم² لا معنى له: شريحة بعرض
1 مم على جدار 3 م تبلغ 3000 مم².
"""


def verify_tiling(rects: dict[str, Rect], env: Rect) -> None:
    """
    يتحقّق أن المستطيلات تبلّط المظروف تمامًا: بلا فراغ ولا تراكب ولا خروج.

    يرفع `ValueError` تحمل لفظ «غير منتظم». الفشل الصريح أرخص من
    طوبولوجيا مبنية على تبليط ناقص: تلك تبدو صحيحة حتى أول سحبة جدار، ثم
    تُفقد غرفة أو ينفتح فراغ بلا رسالة تدلّ على الموضع.

    يُستدعى من `build_topology` (فيحرس المحرر)، ومن `align_storeys`
    (فيحرس التقريب الرأسي).
    """
    if not rects:
        raise ValueError("تبليط غير منتظم: لا غرف")

    for rid, r in sorted(rects.items()):
        if not env.contains(r):
            raise ValueError(
                f"تبليط غير منتظم: الغرفة {rid} "
                f"({r.x},{r.y})–({r.x2},{r.y2}) خارج المظروف "
                f"({env.x},{env.y})–({env.x2},{env.y2})"
            )

    total = sum(r.area for r in rects.values())
    gap = env.area - total
    if abs(gap) > env.area * TILING_TOL_RATIO:
        kind = "فراغ غير مُخصَّص" if gap > 0 else "تجاوز مجموع المساحات"
        raise ValueError(
            f"تبليط غير منتظم: {kind} {abs(gap)} مم² "
            f"(المجموع {total}، المظروف {env.area})"
        )

    items = sorted(rects.items())
    for i, (ia, a) in enumerate(items):
        for ib, b in items[i + 1:]:
            if a.overlap_area(b) > TOL * TOL:
                raise ValueError(
                    f"تبليط غير منتظم: تراكب بين {ia} و {ib} "
                    f"({a.overlap_area(b)} مم²)"
                )
