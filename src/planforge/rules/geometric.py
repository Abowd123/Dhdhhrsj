"""
القواعد الهندسية والبرنامجية — تُقاس على **خطوط المراكز**.

هذه أول طبقة تدقيق من أربع. لا تكفي وحدها: `rules/drawing_rules.py`
يعيد القياس على الأوجه الداخلية بعد رسم الجدران، وهناك تسقط مخططات
جازت هنا. الترتيب مقصود، لا تكرار.
"""
from __future__ import annotations
from typing import Iterable
from planforge.codes.uk.detail_profile import DETAIL
from planforge.codes.uk.profile import UK
from planforge.enums import (
    CIRCULATION, NEEDS_PURGE_VENT, RelationKind, RoomType, WET,
)
from planforge.geometry.graph import (
    entrance_room, reachable_via_circulation, vertical_pairs,
)
from planforge.model.brief import Brief
from planforge.model.layout import Layout
from planforge.rules.core import Rule, Severity, Violation
from planforge.units import TOL, fmt_area, fmt_m

TILING_TOL_RATIO = DETAIL.tiling_tol_ratio
STAIR_STACK_MIN_OVERLAP = DETAIL.stair_stack_min_overlap
WET_STACK_MIN_OVERLAP = DETAIL.wet_stack_min_overlap


def _has(brief: Brief, room_id: str) -> bool:
    try:
        brief.room(room_id)
        return True
    except KeyError:
        return False


def _door(brief: Brief) -> int:
    return UK.door_min_clear_width[brief.access_standard]


def _hosts(brief: Brief) -> frozenset[str]:
    return frozenset(r.access_via for r in brief.rooms if r.access_via)


# ─────────────────── سلامة هندسية ───────────────────

def r_no_overlap(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for s in layout.storeys:
        rooms = s.rooms
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                ov = rooms[i].r.overlap_area(rooms[j].r)
                if ov > TOL * TOL:
                    yield Violation(
                        "GEO-001", Severity.ERROR, "تراكب بين غرفتين",
                        "سلامة هندسية", s.index,
                        (rooms[i].id, rooms[j].id), fmt_area(ov), "0",
                    )


def r_within_envelope(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for s in layout.storeys:
        env = s.envelope.to_rect()
        for r in s.rooms:
            if not env.contains(r.r):
                yield Violation(
                    "GEO-002", Severity.ERROR, "غرفة خارج مظروف البناء",
                    "الارتدادات", s.index, (r.id,),
                    f"({r.r.x},{r.r.y})–({r.r.x2},{r.r.y2})",
                    f"({env.x},{env.y})–({env.x2},{env.y2})",
                )


def r_full_tiling(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    التبليط تام: لا فراغ غير مُسمّى ولا تجاوز.

    شبكة أمان لا فحص أولي: بنية شجرة القطع في المُحلّل تضمن التبليط
    بالبناء. سقوط هذه القاعدة يعني خطأً في المُحلّل أو في المحرر، لا
    مخالفة تصميمية.
    """
    for s in layout.storeys:
        env = s.envelope.to_rect()
        total = sum(r.r.area for r in s.rooms)
        gap = env.area - total
        if abs(gap) > env.area * TILING_TOL_RATIO:
            label = "فراغ غير مُخصَّص" if gap > 0 else "تجاوز مجموع المساحات"
            yield Violation(
                "GEO-003", Severity.ERROR, f"{label} داخل المظروف",
                "سلامة هندسية", s.index, (),
                fmt_area(abs(gap)), "≈ 0",
            )


def r_min_dimensions(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for s in layout.storeys:
        for r in s.rooms:
            declared = (
                brief.room(r.id).min_width_mm if _has(brief, r.id) else None
            )
            floor = max(
                declared or 0, UK.practical_min_width.get(r.type, 0)
            )
            if floor and r.r.min_dim < floor:
                yield Violation(
                    "GEO-004", Severity.ERROR,
                    "أصغر بعد للغرفة دون الحد العملي",
                    "عرف مهني", s.index, (r.id,),
                    fmt_m(r.r.min_dim), fmt_m(floor),
                )


def r_aspect_ratio(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for s in layout.storeys:
        for r in s.rooms:
            if r.type in CIRCULATION:
                continue
            declared = (
                brief.room(r.id).max_aspect if _has(brief, r.id) else None
            )
            cap = declared or UK.max_aspect_default
            if r.r.aspect > cap:
                yield Violation(
                    "GEO-005", Severity.WARN,
                    "نسبة باعية مفرطة (غرفة أنبوبية)",
                    "عرف مهني", s.index, (r.id,),
                    f"{r.r.aspect:.2f}", f"≤ {cap:.2f}",
                )


def r_area_within_brief(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for r in layout.all_rooms():
        if not _has(brief, r.id):
            continue
        req = brief.room(r.id)
        lo = req.min_area_mm2 or int(req.target_area_mm2 * 0.85)
        hi = req.max_area_mm2 or int(req.target_area_mm2 * 1.25)
        if not (lo <= r.r.area <= hi):
            yield Violation(
                "GEO-006", Severity.WARN,
                "مساحة الغرفة خارج مجال المتطلب",
                "المتطلب", r.storey, (r.id,),
                fmt_area(r.r.area), f"{fmt_area(lo)} – {fmt_area(hi)}",
            )


# ─────────────────── الوصول ───────────────────

def r_reachability(layout: Layout, brief: Brief) -> Iterable[Violation]:
    door = _door(brief)
    hosts = _hosts(brief)
    for s in layout.storeys:
        start = entrance_room(s)
        if start is None:
            yield Violation(
                "GEO-007", Severity.ERROR,
                "لا توجد مساحة حركة في هذا الدور",
                "سلامة الوصول", s.index,
            )
            continue
        reachable = reachable_via_circulation(s, start.id, door, hosts)
        for r in s.rooms:
            if r.id not in reachable:
                yield Violation(
                    "GEO-008", Severity.ERROR,
                    "غرفة غير قابلة للوصول من الحركة",
                    "سلامة الوصول", s.index, (r.id,),
                )


def r_external_wall(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for s in layout.storeys:
        env = s.envelope.to_rect()
        for r in s.rooms:
            needs = (
                brief.room(r.id).requires_external_wall
                if _has(brief, r.id) else None
            )
            if needs is None:
                needs = r.type in NEEDS_PURGE_VENT
            if needs and r.r.external_perimeter(env) <= 0:
                yield Violation(
                    "GEO-009", Severity.ERROR,
                    "غرفة تحتاج واجهة خارجية ولا تملك أيًّا منها",
                    "إضاءة/تهوية", s.index, (r.id,),
                )


# ─────────────────── النواة الرأسية ───────────────────

def r_stair_alignment(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    السلّم فوق بعضه في كل الأدوار.

    قيد إنشائي لا تفضيل: نواة غير متطابقة تعني نقل أحمال أفقيًا، وتُفقد
    الجدران المحيطة تصنيفها الحامل في `structural_lines`.
    """
    per_storey = {
        s.index: [
            r for r in s.rooms
            if r.type in {RoomType.STAIR, RoomType.LANDING}
        ]
        for s in layout.storeys
    }
    idxs = sorted(per_storey)
    for lo, hi in zip(idxs, idxs[1:]):
        a, b = per_storey[lo], per_storey[hi]
        if not a or not b:
            continue
        ratio, aid, bid = max(
            (x.r.overlap_area(y.r) / min(x.r.area, y.r.area), x.id, y.id)
            for x in a for y in b
        )
        if ratio < STAIR_STACK_MIN_OVERLAP:
            yield Violation(
                "GEO-010", Severity.ERROR,
                "نواة السلّم غير متطابقة رأسيًا بين الدورين",
                "سلامة إنشائية", hi, (aid, bid),
                f"تراكب {ratio:.0%}", f"≥ {STAIR_STACK_MIN_OVERLAP:.0%}",
            )


def r_wet_stack(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """محاذاة الغرف الرطبة رأسيًا: عمود مواسير واحد بدل مجاري أفقية."""
    stacked = {
        b.id for a, b in vertical_pairs(layout)
        if a.type in WET and b.type in WET
        and a.r.overlap_area(b.r) > min(a.r.area, b.r.area)
        * WET_STACK_MIN_OVERLAP
    }
    lowest = min((s.index for s in layout.storeys), default=0)
    for s in layout.storeys:
        if s.index == lowest:
            continue
        for r in s.rooms:
            if r.type in WET and r.id not in stacked:
                yield Violation(
                    "GEO-011", Severity.WARN,
                    "غرفة رطبة غير محاذية لغرفة رطبة في الدور الأسفل",
                    "كفاءة تنفيذية", s.index, (r.id,),
                )


# ─────────────────── علاقات المتطلب ───────────────────

def r_relations(layout: Layout, brief: Brief) -> Iterable[Violation]:
    door = _door(brief)
    for rel in brief.relations:
        try:
            a, b = layout.find(rel.a), layout.find(rel.b)
        except KeyError:
            continue
        sev = Severity.ERROR if rel.hard else Severity.WARN

        if rel.kind is RelationKind.SAME_STOREY:
            if a.storey != b.storey:
                yield Violation(
                    "GEO-012", sev, "علاقة نفس الدور غير محققة",
                    "المتطلب", None, (a.id, b.id),
                    f"{a.storey} / {b.storey}", "دور واحد",
                )
            continue

        if rel.kind is RelationKind.STACKED:
            ov = a.r.overlap_area(b.r)
            if ov < min(a.r.area, b.r.area) * 0.80:
                yield Violation(
                    "GEO-013", sev, "علاقة التراكب الرأسي غير محققة",
                    "المتطلب", None, (a.id, b.id), fmt_area(ov), "≥ 80%",
                )
            continue

        if a.storey != b.storey:
            if rel.kind in {
                RelationKind.ADJACENT, RelationKind.DIRECT_ACCESS
            }:
                yield Violation(
                    "GEO-014", sev, "غرفتا العلاقة في دورين مختلفين",
                    "المتطلب", None, (a.id, b.id),
                    f"{a.storey} / {b.storey}", "دور واحد",
                )
            continue

        shared, _ = a.r.shared_edge(b.r)
        if rel.kind is RelationKind.ADJACENT and shared <= 0:
            yield Violation(
                "GEO-015", sev, "التلاصق المطلوب غير محقق",
                "المتطلب", a.storey, (a.id, b.id), "0", "> 0",
            )
        elif rel.kind is RelationKind.DIRECT_ACCESS and shared < door:
            yield Violation(
                "GEO-016", sev, "الحد المشترك لا يكفي لباب مباشر",
                "المتطلب", a.storey, (a.id, b.id),
                fmt_m(shared), fmt_m(door),
            )
        elif rel.kind is RelationKind.NOT_ADJACENT and shared > 0:
            yield Violation(
                "GEO-017", sev, "تلاصق ممنوع",
                "المتطلب", a.storey, (a.id, b.id), fmt_m(shared), "0",
            )


# ─────────────────── سلامة الدور الواحد ───────────────────

def r_single_storey_sanity(
    layout: Layout, brief: Brief
) -> Iterable[Violation]:
    """
    دور واحد حالة مدعومة، لا حالة مهملة. فحوصها صريحة كي لا يتسلّل سلّم
    أو بسطة يستهلكان مساحة بلا وظيفة.
    """
    if brief.is_multi_storey:
        if len(layout.storeys) != brief.n_storeys:
            yield Violation(
                "GEO-020", Severity.ERROR,
                "عدد أدوار المخطط يخالف المتطلب",
                "سلامة المتطلب", None, (),
                f"{len(layout.storeys)} دور", f"{brief.n_storeys} دور",
            )
        return

    for r in layout.all_rooms():
        if r.type is RoomType.STAIR:
            yield Violation(
                "GEO-018", Severity.ERROR,
                "سلّم في مبنى بدور واحد — مساحة مهدورة",
                "سلامة المتطلب", r.storey, (r.id,),
            )
        elif r.type is RoomType.LANDING:
            yield Violation(
                "GEO-019", Severity.WARN,
                "بسطة سلّم في مبنى بدور واحد",
                "سلامة المتطلب", r.storey, (r.id,),
            )
    if len(layout.storeys) != 1:
        yield Violation(
            "GEO-020", Severity.ERROR,
            "المتطلب دور واحد والمخطط يحتوي أدوارًا متعددة",
            "سلامة المتطلب", None, (),
            f"{len(layout.storeys)} دور", "1",
        )


GEOMETRIC_RULES: list[Rule] = [
    Rule("GEO-OVERLAP", "عدم التراكب", "سلامة هندسية",
         r_no_overlap, frozenset({"geometry"}), ("GEO-001",)),
    Rule("GEO-ENVELOPE", "الاحتواء في المظروف", "الارتدادات",
         r_within_envelope, frozenset({"geometry"}), ("GEO-002",)),
    Rule("GEO-TILING", "التبليط الكامل", "سلامة هندسية",
         r_full_tiling, frozenset({"geometry"}), ("GEO-003",)),
    Rule("GEO-MINDIM", "الأبعاد الدنيا", "عرف مهني",
         r_min_dimensions, frozenset({"geometry"}), ("GEO-004",)),
    Rule("GEO-ASPECT", "النسبة الباعية", "عرف مهني",
         r_aspect_ratio, frozenset({"geometry"}), ("GEO-005",)),
    Rule("GEO-AREA", "مطابقة المساحات للمتطلب", "المتطلب",
         r_area_within_brief, frozenset({"program"}), ("GEO-006",)),
    Rule("GEO-REACH", "قابلية الوصول", "سلامة الوصول",
         r_reachability, frozenset({"circulation"}), ("GEO-007", "GEO-008")),
    Rule("GEO-EXTWALL", "الواجهة الخارجية", "إضاءة/تهوية",
         r_external_wall, frozenset({"geometry"}), ("GEO-009",)),
    Rule("GEO-STAIRALIGN", "محاذاة نواة السلّم", "سلامة إنشائية",
         r_stair_alignment, frozenset({"vertical"}), ("GEO-010",)),
    Rule("GEO-WETSTACK", "محاذاة المواسير", "كفاءة تنفيذية",
         r_wet_stack, frozenset({"vertical"}), ("GEO-011",)),
    Rule("GEO-RELATIONS", "علاقات المتطلب", "المتطلب",
         r_relations, frozenset({"program"}),
         ("GEO-012", "GEO-013", "GEO-014", "GEO-015", "GEO-016", "GEO-017")),
    Rule("GEO-SINGLE", "سلامة الدور الواحد", "سلامة المتطلب",
         r_single_storey_sanity, frozenset({"geometry", "vertical"}),
         ("GEO-018", "GEO-019", "GEO-020")),
]
