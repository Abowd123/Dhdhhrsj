"""
اشتقاق شبكة الجدران من تبليط الغرف.

مستطيلات المُحلّل خطوط مراكز. لكل خط نجمع المقاطع التي يوجد فيها جدار
فعلًا — حدّ المظروف أو حدّ بين غرفتين — نصنّف السماكة، ثم ندمج المتصل
المتشابه في مسارات (runs).

تحديد الجدران الحاملة: خط مستمر على ≥60% من بُعد المظروف، وموجود في
**كل** الأدوار داخل سماحية. الاستمرارية والمحاذاة الرأسية هما تعريف
الجدار الحامل عمليًا: جدار في دور بلا سنَد أسفله ليس حاملًا. ما دونه
قاطع خفيف.
"""
from __future__ import annotations
from planforge.codes.uk.detail_profile import DETAIL
from planforge.drawing.model import WallFace, WallKind, WallRun
from planforge.enums import Axis, RoomType
from planforge.geometry.rect import Rect
from planforge.geometry.tiling import Segment, segments_on_axis
from planforge.model.brief import WallSpec
from planforge.units import TOL

STRUCTURAL_MIN_RATIO = DETAIL.structural_min_ratio
ALIGN_TOL_MM = DETAIL.vertical_align_tol_mm
STAIR_TYPES = frozenset({RoomType.STAIR, RoomType.LANDING})


def structural_lines(
    storey_rects: list[tuple[Rect, dict[str, Rect]]]
) -> tuple[frozenset[int], frozenset[int]]:
    """
    الخطوط الحاملة = مستمرة على ≥60% من بُعد المظروف في كل الأدوار.

    التقاطع بين الأدوار هو الشرط الإنشائي. حدود المظروف مستثناة: هي
    خارجية بحكم موضعها لا بحكم استمراريتها.
    """
    per_x: list[set[int]] = []
    per_y: list[set[int]] = []

    for env, rects in storey_rects:
        for axis, sink, span in (
            (Axis.V, per_x, env.h), (Axis.H, per_y, env.w)
        ):
            totals: dict[int, int] = {}
            for s in segments_on_axis(rects, env, axis):
                if s.is_external:
                    continue
                totals[s.coord] = totals.get(s.coord, 0) + s.length
            sink.append({
                c for c, t in totals.items()
                if t >= span * STRUCTURAL_MIN_RATIO
            })

    def _intersect(sets: list[set[int]]) -> frozenset[int]:
        if not sets:
            return frozenset()
        return frozenset(
            c for c in sets[0]
            if all(
                any(abs(c - d) <= ALIGN_TOL_MM for d in s) for s in sets[1:]
            )
        )

    return _intersect(per_x), _intersect(per_y)


def party_lines(
    env: Rect, setbacks
) -> tuple[frozenset[int], frozenset[int]]:
    """
    الجدران المشتركة: جهات المظروف الملامسة لحدود الأرض تمامًا.

    ارتداد صفر يعني بناءً على الحد، أي جدار مشترك مع الجار لا واجهة —
    وهذا يغيّر سماكته وتصنيفه في التصدير.
    """
    px: set[int] = set()
    py: set[int] = set()
    if setbacks.left_mm == 0:
        px.add(env.x)
    if setbacks.right_mm == 0:
        px.add(env.x2)
    if setbacks.front_mm == 0:
        py.add(env.y)
    if setbacks.rear_mm == 0:
        py.add(env.y2)
    return frozenset(px), frozenset(py)


def _classify(
    seg: Segment,
    spec: WallSpec,
    structural: frozenset[int],
    protected_ids: frozenset[str],
    party: frozenset[int],
) -> tuple[WallKind, int]:
    if seg.is_external:
        if seg.coord in party:
            return WallKind.PARTY, spec.party_mm
        return WallKind.EXTERNAL, spec.external_mm
    if protected_ids and (
        (seg.a in protected_ids) != (seg.b in protected_ids)
    ):
        return WallKind.FIRE, spec.internal_loadbearing_mm
    if any(abs(seg.coord - s) <= ALIGN_TOL_MM for s in structural):
        return WallKind.LOADBEARING, spec.internal_loadbearing_mm
    return WallKind.PARTITION, spec.internal_partition_mm


def build_faces(
    rects: dict[str, Rect],
    types: dict[str, RoomType],
    env: Rect,
    spec: WallSpec,
    *,
    structural_x: frozenset[int],
    structural_y: frozenset[int],
    protected_stair: bool,
    party_x: frozenset[int] = frozenset(),
    party_y: frozenset[int] = frozenset(),
) -> list[WallFace]:
    protected = (
        frozenset(i for i, t in types.items() if t in STAIR_TYPES)
        if protected_stair else frozenset()
    )
    faces: list[WallFace] = []
    for axis, structural, party in (
        (Axis.V, structural_x, party_x), (Axis.H, structural_y, party_y)
    ):
        for seg in segments_on_axis(rects, env, axis):
            kind, t = _classify(seg, spec, structural, protected, party)
            faces.append(WallFace(
                axis=seg.axis, coord=seg.coord, lo=seg.lo, hi=seg.hi,
                a=seg.a, b=seg.b, kind=kind, thickness_mm=t,
            ))
    return faces


def merge_runs(faces: list[WallFace]) -> list[WallRun]:
    """دمج المقاطع المتلاصقة على نفس الخط وبنفس النوع في مسار واحد."""
    buckets: dict[tuple[Axis, int, WallKind, int], list[WallFace]] = {}
    for f in faces:
        buckets.setdefault(
            (f.axis, f.coord, f.kind, f.thickness_mm), []
        ).append(f)

    runs: list[WallRun] = []
    n = 0
    for (axis, coord, kind, t), group in sorted(
        buckets.items(), key=lambda kv: (kv[0][0].value, kv[0][1], kv[0][2])
    ):
        group.sort(key=lambda f: (f.lo, f.hi))
        cur: list[WallFace] = [group[0]]
        for f in group[1:]:
            if f.lo - cur[-1].hi <= TOL:
                cur.append(f)
            else:
                n += 1
                runs.append(WallRun(
                    f"W{n:03d}", axis, coord, cur[0].lo, cur[-1].hi,
                    kind, t, tuple(cur),
                ))
                cur = [f]
        n += 1
        runs.append(WallRun(
            f"W{n:03d}", axis, coord, cur[0].lo, cur[-1].hi,
            kind, t, tuple(cur),
        ))
    return runs


def clear_rooms(
    rects: dict[str, Rect], faces: list[WallFace]
) -> dict[str, Rect]:
    """
    إزاحة كل غرفة بنصف سماكة الجدار على كل ضلع.

    عند تعدد السماكات على ضلع واحد نأخذ الأكبر — تحفّظ مقصود: لا نُبلّغ
    عن مساحة صافية أكبر من الواقع. الاتجاه الصحيح للخطأ في أداة تدقيق.
    """
    insets: dict[str, dict[str, int]] = {
        i: {"L": 0, "R": 0, "B": 0, "T": 0} for i in rects
    }
    for f in faces:
        half = f.thickness_mm // 2
        if f.axis is Axis.V:
            if f.a:
                insets[f.a]["R"] = max(insets[f.a]["R"], half)
            if f.b:
                insets[f.b]["L"] = max(insets[f.b]["L"], half)
        else:
            if f.a:
                insets[f.a]["T"] = max(insets[f.a]["T"], half)
            if f.b:
                insets[f.b]["B"] = max(insets[f.b]["B"], half)

    out: dict[str, Rect] = {}
    for i, r in rects.items():
        d = insets[i]
        w = r.w - d["L"] - d["R"]
        h = r.h - d["B"] - d["T"]
        # غرفة استهلكتها الجدران: نُبقيها بأصغر بعد ممكن ليلتقطها DRW-017
        out[i] = Rect(r.x + d["L"], r.y + d["B"], max(w, 1), max(h, 1))
    return out


def internal_envelope(env: Rect, spec: WallSpec) -> Rect:
    """المظروف بين أوجه الجدران الخارجية — أساس قياس GIA الصافية."""
    half = spec.external_mm // 2
    return Rect(env.x + half, env.y + half, env.w - 2 * half, env.h - 2 * half)
