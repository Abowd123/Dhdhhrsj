"""
التدقيق الثالث — على الأبعاد الصافية.

الطبقتان السابقتان قاستا على خطوط المراكز. هنا القياس على أوجه الجدران،
وهو الأساس القانوني في NDSS و ADM. مخطط جاز التدقيق الأول قد يسقط هنا،
وهذا هو الغرض: أن يسقط قبل التسليم لا بعده.

وهنا وحدها تُفحص أشياء لا وجود لها قبل رسم الجدران: هل الفتحة تقع داخل
حدود جدارها؟ هل بقي كتفٌ لإطارها؟ هل التهوية متحققة بالفتح المرسوم لا
بالمُعلن؟
"""
from __future__ import annotations
from typing import Iterable
from planforge.codes.uk.detail_profile import DETAIL
from planforge.codes.uk.profile import UK
from planforge.drawing.model import Drawing, WallKind
from planforge.drawing.placement import FRAME_MM
from planforge.enums import (
    BEDROOMS, CIRCULATION, NEEDS_PURGE_VENT, OpeningKind, RoomType,
)
from planforge.model.brief import Brief
from planforge.rules.core import ComplianceReport, Rule, Severity, Violation
from planforge.units import fmt_area, fmt_m

MIN_WALL_SLIVER_MM = DETAIL.wall_sliver_min_mm
SWING_CLEARANCE_MM = DETAIL.swing_clearance_mm

DOOR_KINDS = frozenset({OpeningKind.DOOR, OpeningKind.FIRE_DOOR})
STAIR_TYPES = frozenset({RoomType.STAIR, RoomType.LANDING})


def _door_w(brief: Brief) -> int:
    return UK.door_min_clear_width[brief.access_standard]


# ═══════════════════ المساحات والأبعاد الصافية ═══════════════════

def d_clear_room_areas(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    for s in dwg.storeys:
        for r in s.rooms:
            if r.type not in BEDROOMS:
                continue
            need_a = UK.bedroom_min_area[r.type]
            need_w = UK.bedroom_min_width[r.type]
            if r.area < need_a:
                yield Violation(
                    "DRW-001", Severity.ERROR,
                    "المساحة الصافية لغرفة النوم دون NDSS بعد رسم الجدران",
                    "NDSS 2015 para 10 (قياس صافٍ)", s.index, (r.id,),
                    f"{fmt_area(r.area)} "
                    f"(خط المركز {fmt_area(r.centerline_area_mm2)})",
                    fmt_area(need_a),
                )
            if r.min_dim < need_w:
                yield Violation(
                    "DRW-002", Severity.ERROR,
                    "العرض الصافي لغرفة النوم دون NDSS",
                    "NDSS 2015 para 10 (قياس صافٍ)", s.index, (r.id,),
                    fmt_m(r.min_dim), fmt_m(need_w),
                )


def d_clear_min_dims(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    for s in dwg.storeys:
        for r in s.rooms:
            floor = UK.practical_min_width.get(r.type)
            if floor and r.min_dim < floor:
                yield Violation(
                    "DRW-003", Severity.ERROR,
                    "أصغر بعد صافٍ دون الحد العملي",
                    "عرف مهني (قياس صافٍ)", s.index, (r.id,),
                    fmt_m(r.min_dim), fmt_m(floor),
                )


def d_corridor_clear_width(
    dwg: Drawing, brief: Brief
) -> Iterable[Violation]:
    need = UK.corridor_min_width[brief.access_standard]
    for s in dwg.storeys:
        for r in s.rooms:
            if r.type not in CIRCULATION or r.type is RoomType.STAIR:
                continue
            if r.min_dim < need:
                yield Violation(
                    "DRW-004", Severity.ERROR,
                    "العرض الصافي للممر دون ADM بعد رسم الجدران",
                    f"ADM Vol 1 {brief.access_standard} Table 2",
                    s.index, (r.id,), fmt_m(r.min_dim), fmt_m(need),
                )


def d_gia_clear(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    """
    الحكم المعتبر على GIA. `NDSS-003` قاسها على خطوط المراكز فبالغ؛ هذا
    القياس بين أوجه الجدران الخارجية.
    """
    need = UK.ndss_gia(
        brief.bedspaces, brief.n_bedrooms, brief.n_storeys
    )
    if need is None:
        return
    gia = dwg.total_gia_mm2
    if gia < need:
        yield Violation(
            "DRW-005", Severity.ERROR,
            "المساحة الداخلية الإجمالية الصافية دون NDSS",
            "NDSS 2015 Table 1 (قياس صافٍ)", None, (),
            fmt_area(gia), fmt_area(need),
        )


# ═══════════════════ هندسة الفتحات ═══════════════════

def d_opening_geometry(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    need = _door_w(brief)
    for s in dwg.storeys:
        by_id = {r.id: r for r in s.rooms}
        for o in s.openings:
            if o.is_door:
                if o.clear_width_mm < need:
                    yield Violation(
                        "DRW-006", Severity.ERROR,
                        f"الخلوص المرسوم للباب {o.id} دون ADM",
                        f"ADM Vol 1 {brief.access_standard} Table 2",
                        s.index, o.rooms(),
                        f"{o.clear_width_mm} مم", f"{need} مم",
                    )
                room = by_id.get(o.swing_to or "")
                if room is not None and room.min_dim < (
                    o.clear_width_mm + SWING_CLEARANCE_MM
                ):
                    yield Violation(
                        "DRW-007", Severity.WARN,
                        f"دوران الباب {o.id} يستهلك عرض الغرفة بالكامل",
                        "عرف مهني", s.index, (room.id,),
                        fmt_m(room.min_dim),
                        fmt_m(o.clear_width_mm + SWING_CLEARANCE_MM),
                    )

            run = s.run_carrying(o)
            if run is None:
                yield Violation(
                    "DRW-008", Severity.ERROR,
                    f"الفتحة {o.id} تتجاوز حدود جدارها أو تعبر وصلة",
                    "سلامة هندسية", s.index, o.rooms(),
                    f"{o.start}–{o.end} على {o.axis} {o.coord}",
                    "داخل مسار جدار واحد",
                )
                continue
            slack = min(o.start - run.lo, run.hi - o.end)
            if slack < FRAME_MM:
                yield Violation(
                    "DRW-009", Severity.ERROR,
                    f"لا كتف كافٍ لإطار الفتحة {o.id} عند طرف الجدار",
                    "سلامة تنفيذية", s.index, o.rooms(),
                    f"{slack} مم", f"≥ {FRAME_MM} مم",
                )


def d_purge_realisable(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    """
    التهوية على الفتح **المرسوم** لا على رقم مُفترض.

    `ADF-001` قاسها على `openable_area_mm2` كما أعلنته طبقة الصقل. هنا
    الرقم مقيَّد بما تسمح به الواجهة فعلًا بعد خصم الزوايا وحصر العرض،
    والمساحة الصافية أصغر من مساحة خط المركز — فالبسط ينقص والمقام ينقص،
    ولا يُعرف أيهما غلب إلا بالقياس بعد الرسم.
    """
    for s in dwg.storeys:
        got: dict[str, int] = {}
        for o in s.openings:
            if o.room_b is None and o.is_window:
                got[o.room_a] = got.get(o.room_a, 0) + o.openable_area_mm2
        for r in s.rooms:
            if r.type not in NEEDS_PURGE_VENT:
                continue
            need = int(r.area * UK.purge_vent_ratio)
            have = got.get(r.id, 0)
            if have < need:
                yield Violation(
                    "DRW-010", Severity.ERROR,
                    "الفتح القابل للتشغيل المرسوم دون النسبة المطلوبة من "
                    "المساحة الصافية",
                    "ADF Vol 1 2021 Table 1.3 (هندسة مرسومة)",
                    s.index, (r.id,), fmt_area(have), fmt_area(need),
                )


def d_escape_window_geometry(
    dwg: Drawing, brief: Brief
) -> Iterable[Violation]:
    lo, hi = UK.escape_window_sill_range
    for s in dwg.storeys:
        for o in s.openings:
            if o.kind is not OpeningKind.ESCAPE_WINDOW:
                continue
            if o.openable_area_mm2 < UK.escape_window_min_area:
                yield Violation(
                    "DRW-011", Severity.ERROR,
                    f"نافذة الهروب {o.id}: الفتح المرسوم دون الحد",
                    "ADB Vol 1 2019 para 2.10 (هندسة مرسومة)",
                    s.index, (o.room_a,),
                    fmt_area(o.openable_area_mm2),
                    fmt_area(UK.escape_window_min_area),
                )
            if o.clear_width_mm < UK.escape_window_min_dim:
                yield Violation(
                    "DRW-012", Severity.ERROR,
                    f"نافذة الهروب {o.id}: العرض المرسوم دون الحد",
                    "ADB Vol 1 2019 para 2.10 (هندسة مرسومة)",
                    s.index, (o.room_a,),
                    f"{o.clear_width_mm} مم",
                    f"{UK.escape_window_min_dim} مم",
                )
            if not (lo <= o.sill_mm <= hi):
                yield Violation(
                    "DRW-013", Severity.ERROR,
                    f"نافذة الهروب {o.id}: منسوب الجلسة خارج المجال",
                    "ADB Vol 1 2019 para 2.10", s.index, (o.room_a,),
                    f"{o.sill_mm} مم", f"{lo}–{hi} مم",
                )


def d_fire_enclosure(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    """
    محيط السلّم المحمي: أبواب مصنَّفة وجدران غير خفيفة.

    `ADB-003` فحص الأبواب على رسم الوصول. هنا الفحص على الفتحات المرسومة
    فعلًا وعلى **الجدران** نفسها — وهذا ما لا يُقاس قبل التصنيف: قاطعٌ
    بسماكة 100 مم لا يحمل تصنيف مقاومة، وسلّمٌ محاطٌ به غير محمي حتى لو
    كانت كل أبوابه FD30.
    """
    label = f"FD{UK.fire_rating_minutes_int}"
    for s in dwg.storeys:
        if not s.protected_stair:
            continue
        stair_ids = {r.id for r in s.rooms if r.type in STAIR_TYPES}
        if not stair_ids:
            continue
        types = {r.id: r.type for r in s.rooms}

        for o in s.openings:
            rooms = set(o.rooms())
            if not (rooms & stair_ids):
                continue
            other = rooms - stair_ids
            if not other:
                continue
            oid = next(iter(sorted(other)))
            if types.get(oid) in CIRCULATION:
                continue
            if o.fire_rating != label:
                yield Violation(
                    "DRW-014", Severity.ERROR,
                    "فتحة على السلّم المحمي بلا تصنيف مقاومة",
                    "ADB Vol 1 2019 para 2.6 / Appendix C",
                    s.index, (o.room_a, oid),
                    o.fire_rating or "بلا تصنيف", label,
                )

        enclosing = [
            f for f in s.faces
            if not f.is_external and len(f.rooms() & stair_ids) == 1
        ]
        weak = [f for f in enclosing if f.kind is WallKind.PARTITION]
        if weak:
            total = sum(f.length for f in weak)
            yield Violation(
                "DRW-015", Severity.ERROR,
                f"{len(weak)} مقطعًا من محيط السلّم المحمي بقاطع غير مصنَّف",
                "ADB Vol 1 2019 para 2.6", s.index,
                tuple(sorted(stair_ids)),
                f"{fmt_m(total)} قاطع خفيف", "جدار مصنَّف على كل المحيط",
            )


def d_wall_slivers(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    for s in dwg.storeys:
        for run in s.runs:
            if run.length < MIN_WALL_SLIVER_MM:
                yield Violation(
                    "DRW-016", Severity.WARN,
                    f"مقطع جدار {run.id} أقصر من الحد — شظية تنفيذية",
                    "سلامة تنفيذية", s.index,
                    tuple(sorted(run.rooms())),
                    f"{run.length} مم", f"≥ {MIN_WALL_SLIVER_MM} مم",
                )
        for r in s.rooms:
            if r.w <= 1 or r.h <= 1:
                yield Violation(
                    "DRW-017", Severity.ERROR,
                    "الجدران استهلكت الغرفة بالكامل",
                    "سلامة هندسية", s.index, (r.id,),
                    f"{r.w}×{r.h} مم "
                    f"(خط المركز {fmt_area(r.centerline_area_mm2)})",
                    "> 0",
                )


def d_every_room_has_door(dwg: Drawing, brief: Brief) -> Iterable[Violation]:
    """
    باب مرسوم لكل غرفة غير حركية.

    `GEO-008` فحص قابلية الوصول على التلاصق. هذه القاعدة تفحص أن الباب
    **حُلّ هندسيًا**: غرفة تلامس الحركة بجدار طويل قد يفشل حل بابها
    لأسباب الكتف أو الوصلة، فتظهر في مخرج مكتمل المظهر بلا منفذ.
    """
    for s in dwg.storeys:
        served: set[str] = set()
        for o in s.openings:
            if o.kind in DOOR_KINDS or o.kind is OpeningKind.OPEN:
                served.update(o.rooms())
        for r in s.rooms:
            if r.type in CIRCULATION:
                continue
            if r.id not in served:
                yield Violation(
                    "DRW-018", Severity.ERROR,
                    "غرفة بلا باب مرسوم",
                    "سلامة الوصول", s.index, (r.id,),
                    "0 باب", "≥ 1",
                )


DRAWING_CHECKS: list[Rule] = [
    Rule("DRW-AREA", "المساحات الصافية لغرف النوم",
         "NDSS para 10 (صافٍ)", d_clear_room_areas,
         frozenset({"drawing", "space"}), ("DRW-001", "DRW-002")),
    Rule("DRW-MINDIM", "الأبعاد الصافية الدنيا",
         "عرف مهني (صافٍ)", d_clear_min_dims,
         frozenset({"drawing", "space"}), ("DRW-003",)),
    Rule("DRW-CORR", "عرض الممر الصافي",
         "ADM Table 2 (صافٍ)", d_corridor_clear_width,
         frozenset({"drawing", "access"}), ("DRW-004",)),
    Rule("DRW-GIA", "المساحة الإجمالية الصافية",
         "NDSS Table 1 (صافٍ)", d_gia_clear,
         frozenset({"drawing", "space"}), ("DRW-005",)),
    Rule("DRW-OPEN", "هندسة الفتحات",
         "ADM Table 2 / سلامة تنفيذية", d_opening_geometry,
         frozenset({"drawing", "access"}),
         ("DRW-006", "DRW-007", "DRW-008", "DRW-009")),
    Rule("DRW-PURGE", "التهوية المتحقّقة",
         "ADF Table 1.3 (مرسوم)", d_purge_realisable,
         frozenset({"drawing", "vent"}), ("DRW-010",)),
    Rule("DRW-ESC", "هندسة نوافذ الهروب",
         "ADB para 2.10 (مرسوم)", d_escape_window_geometry,
         frozenset({"drawing", "fire"}),
         ("DRW-011", "DRW-012", "DRW-013")),
    Rule("DRW-FIRE", "محيط السلّم المحمي",
         "ADB para 2.6", d_fire_enclosure,
         frozenset({"drawing", "fire"}), ("DRW-014", "DRW-015")),
    Rule("DRW-SLIVER", "شظايا الجدران والغرف المستهلكة",
         "سلامة هندسية", d_wall_slivers,
         frozenset({"drawing", "geometry"}), ("DRW-016", "DRW-017")),
    Rule("DRW-DOOR", "باب لكل غرفة",
         "سلامة الوصول", d_every_room_has_door,
         frozenset({"drawing", "access"}), ("DRW-018",)),
]

DRAWING_CODES: frozenset[str] = frozenset(
    ["DRW-000", *(c for r in DRAWING_CHECKS for c in r.emits)]
)


def check_drawing(
    dwg: Drawing,
    brief: Brief,
    placement_problems: list[str] | None = None,
    tags: set[str] | None = None,
) -> ComplianceReport:
    """
    تشغيل تدقيق الرسم.

    `placement_problems` مخرجُ `build_drawing`: فتحات تعذّر حلّها هندسيًا.
    تُرفع كـ`DRW-000` لا تُطبع في سجل — الفتحة التي لم تُرسَم مخالفةٌ
    كاملة، لا تحذيرُ تنفيذ.
    """
    rep = ComplianceReport(project_name=dwg.project_name)
    rep.rules_run.append("DRW-000")
    for msg in placement_problems or []:
        rep.violations.append(Violation(
            "DRW-000", Severity.ERROR, msg,
            "تعذّر حل الفتحة على الجدار المرسوم",
        ))
    for rule in DRAWING_CHECKS:
        if tags and not (rule.tags & tags):
            continue
        rep.rules_run.extend(rule.emits)
        rep.violations.extend(rule.check(dwg, brief))
    rep.sort()
    return rep
