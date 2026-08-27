"""
قواعد الكود البريطاني — الطبقة الثانية، تُقاس على **خطوط المراكز**.

حدّ هذه الطبقة صريح: كل قياس هنا على خطوط مراكز الجدران، والأساس
القانوني في NDSS و ADM هو البعد الصافي بين الأوجه. فمخطط يجوز
`NDSS-002` هنا قد يسقط في `DRW-002` بعد رسم الجدران. الطبقتان ليستا
تكرارًا: هذه تُوجّه المُحلّل مبكرًا، وتلك تحكم على الهندسة النهائية.

كل مخالفة تحمل مرجع فقرة **مُدّعى**، لا مُصدَّقًا. حالة إثبات كل رقم في
`planforge codes audit`، والمخرجات تُختم `NOT FOR CONSTRUCTION` حتى
تُوقَّع الأرقام التي استند إليها الحكم.
"""
from __future__ import annotations
from typing import Iterable
from planforge.codes.uk.profile import UK, UKCodeProfile, gia_key
from planforge.enums import (
    BEDROOMS, CIRCULATION, HABITABLE, INNER_ROOM_ALLOWED, NEEDS_EXTRACT,
    NEEDS_PURGE_VENT, OpeningKind, RoomType,
)
from planforge.geometry.graph import access_graph, inner_rooms, storey_links
from planforge.geometry.stair import solve_straight_flight
from planforge.model.brief import Brief
from planforge.model.layout import Layout
from planforge.rules.core import Rule, Severity, Violation
from planforge.units import fmt_area, fmt_m

P: UKCodeProfile = UK

WC_TYPES = frozenset({
    RoomType.WC, RoomType.SHOWER_ROOM, RoomType.BATHROOM,
})
STAIR_TYPES = frozenset({RoomType.STAIR, RoomType.LANDING})
FOOD_TYPES = frozenset({RoomType.KITCHEN, RoomType.KITCHEN_DINING})
DOOR_KINDS = frozenset({OpeningKind.DOOR, OpeningKind.FIRE_DOOR})


def _door(brief: Brief) -> int:
    return P.door_min_clear_width[brief.access_standard]


# ═══════════════════════ NDSS ═══════════════════════

def r_ndss_gia(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    المساحة الإجمالية على خطوط المراكز — تُبالغ بـ4–8%.

    `DRW-005` يعيد القياس صافيًا، وهو الحكم المعتبر. هذه القاعدة تكشف
    المتطلب المستحيل مبكرًا: إن سقط هنا فلن ينجح صافيًا أبدًا.
    """
    required = P.ndss_gia(brief.bedspaces, brief.n_bedrooms, brief.n_storeys)
    if required is None:
        yield Violation(
            "NDSS-006", Severity.WARN,
            "لا مدخل مطابق في جدول NDSS لهذا التركيب — لا حد أدنى مفروض",
            "NDSS 2015 Table 1", None, (),
            gia_key(brief.bedspaces, brief.n_bedrooms, brief.n_storeys),
            "صفّ في الجدول",
        )
        return
    gia = sum(s.envelope.to_rect().area for s in layout.storeys)
    if gia < required:
        yield Violation(
            "NDSS-003", Severity.ERROR,
            "المساحة الإجمالية (خط المركز) أقل من الحد الأدنى",
            "NDSS 2015 Table 1", None, (),
            fmt_area(gia), fmt_area(required),
        )


def r_ndss_bedrooms(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for room in layout.all_rooms():
        if room.type not in BEDROOMS:
            continue
        min_a = P.bedroom_min_area[room.type]
        min_w = P.bedroom_min_width[room.type]
        if room.r.area < min_a:
            yield Violation(
                "NDSS-001", Severity.ERROR,
                "مساحة غرفة النوم دون الحد الأدنى",
                "NDSS 2015 para 10", room.storey, (room.id,),
                fmt_area(room.r.area), fmt_area(min_a),
            )
        if room.r.min_dim < min_w:
            yield Violation(
                "NDSS-002", Severity.ERROR,
                "عرض غرفة النوم دون الحد الأدنى",
                "NDSS 2015 para 10", room.storey, (room.id,),
                fmt_m(room.r.min_dim), fmt_m(min_w),
            )


def r_ndss_storage(layout: Layout, brief: Brief) -> Iterable[Violation]:
    required = P.storage_required(brief.n_bedrooms)
    if not required:
        return
    dedicated = sum(
        r.r.area for r in layout.rooms_of_type(RoomType.STORAGE)
    )
    built_in = sum(r.storage_area_mm2 for r in layout.all_rooms())
    total = dedicated + built_in
    if total < required:
        yield Violation(
            "NDSS-004", Severity.ERROR,
            "التخزين الداخلي المدمج أقل من المطلوب",
            "NDSS 2015 para 9", None, (),
            f"{fmt_area(total)} (مخصص {fmt_area(dedicated)} + "
            f"مدمج {fmt_area(built_in)})",
            fmt_area(required),
        )


def r_ndss_ceiling(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    نسبة المساحة بارتفاع ≥ 2.30 م. الشرط في NDSS نسبةُ مساحة لا ارتفاعٌ
    مطلق، فيُقاس هكذا لا بمنع الأسقف المنخفضة.
    """
    for s in layout.storeys:
        spec = brief.storey_spec(s.index)
        total = s.envelope.to_rect().area
        if not total:
            continue
        compliant = sum(
            r.r.area for r in s.rooms
            if (r.ceiling_height_mm or spec.floor_to_ceiling_mm)
            >= P.ceiling_min_height
        )
        ratio = compliant / total
        if ratio < P.ceiling_min_coverage:
            yield Violation(
                "NDSS-005", Severity.ERROR,
                f"نسبة المساحة بارتفاع ≥ {fmt_m(P.ceiling_min_height)} "
                f"دون الحد",
                "NDSS 2015 para 10", s.index, (),
                f"{ratio:.0%}", f"{P.ceiling_min_coverage:.0%}",
            )


# ═══════════════════════ Part K — السلالم ═══════════════════════

def r_adk_stairs(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    هندسة السلّم. الأبعاد مترابطة (2R+G يربط القائمة بالنائمة)، فتُحلّ
    كطقم وتُبلَّغ مفكّكةً: كل مخالفة تستند إلى أرقامها وحدها.
    """
    if not brief.is_multi_storey:
        return
    ordered = sorted(brief.storeys, key=lambda s: s.index)
    for lower, upper in zip(ordered, ordered[1:]):
        f2f = (
            upper.floor_level_mm - lower.floor_level_mm
            or lower.floor_to_floor_mm
        )
        stairs = [
            r for r in layout.storey(lower.index).rooms
            if r.type is RoomType.STAIR
        ]
        if not stairs:
            yield Violation(
                "ADK-000", Severity.ERROR,
                f"لا سلّم في الدور {lower.index} للصعود إلى {upper.index}",
                "ADK 2013 para 1.1", lower.index,
            )
            continue

        for st in stairs:
            sol = solve_straight_flight(
                f2f, st.r,
                max_rise_mm=P.stair_max_rise,
                min_going_mm=P.stair_min_going,
                max_pitch_deg=P.stair_max_pitch_deg,
                twice_rise_plus_going=P.stair_2r_plus_g,
                min_width_mm=P.stair_min_width,
            )
            geom = (
                f"{sol.n_risers} قائمة × {sol.rise_mm:.0f} مم، "
                f"نائمة {sol.going_mm} مم، ميل {sol.pitch_deg:.1f}°"
            )
            two_rg = 2 * sol.rise_mm + sol.going_mm
            lo, hi = P.stair_2r_plus_g

            if sol.going_mm < P.stair_min_going:
                yield Violation(
                    "ADK-001", Severity.ERROR,
                    "النائمة دون الحد الأدنى — المجرى المتاح لا يكفي",
                    "ADK 2013 Table 1.1", lower.index, (st.id,),
                    f"{sol.going_mm} مم ({geom})",
                    f"≥ {P.stair_min_going} مم",
                )
            elif not (lo <= two_rg <= hi):
                yield Violation(
                    "ADK-001", Severity.ERROR,
                    "2R+G خارج المجال المسموح",
                    "ADK 2013 para 1.5", lower.index, (st.id,),
                    f"{two_rg:.0f} مم ({geom})", f"{lo}–{hi} مم",
                )
            elif sol.rise_mm > P.stair_max_rise:
                yield Violation(
                    "ADK-001", Severity.ERROR,
                    "القائمة تتجاوز الحد الأقصى",
                    "ADK 2013 Table 1.1", lower.index, (st.id,),
                    f"{sol.rise_mm:.0f} مم", f"≤ {P.stair_max_rise} مم",
                )

            if sol.pitch_deg > P.stair_max_pitch_deg:
                yield Violation(
                    "ADK-002", Severity.ERROR,
                    "ميل السلّم يتجاوز الحد",
                    "ADK 2013 para 1.7", lower.index, (st.id,),
                    f"{sol.pitch_deg:.1f}°", f"≤ {P.stair_max_pitch_deg}°",
                )

            if st.r.min_dim < P.stair_min_width:
                yield Violation(
                    "ADK-003", Severity.ERROR,
                    "عرض السلّم دون العرف العملي",
                    "ADK 2013 para 1.10 (عرف: ليس حدًّا قانونيًا للسلالم "
                    "الخاصة)", lower.index, (st.id,),
                    fmt_m(st.r.min_dim), fmt_m(P.stair_min_width),
                )

            if sol.fits:
                yield Violation(
                    "ADK-001", Severity.INFO, "حل السلّم مطابق",
                    "ADK 2013 para 1", lower.index, (st.id,), geom,
                )

            # إفصاح لا حكم: خلوص الرأس لا يُقاس من مسقط.
            yield Violation(
                "ADK-004", Severity.INFO,
                f"خلوص الرأس ({fmt_m(P.stair_min_headroom)}) لم يُفحص — "
                f"يحتاج مقطعًا رأسيًا، والنظام يعمل على المساقط فقط",
                "ADK 2013 para 1.10", lower.index, (st.id,),
                "غير مقيس", fmt_m(P.stair_min_headroom),
            )


# ═══════════════════════ Part M — الوصول ═══════════════════════

def r_adm_wc_entrance_storey(
    layout: Layout, brief: Brief
) -> Iterable[Violation]:
    if not P.wc_at_entrance_storey_required:
        return
    entrance = min(s.index for s in layout.storeys)
    if not any(r.type in WC_TYPES for r in layout.storey(entrance).rooms):
        yield Violation(
            "ADM-003", Severity.ERROR,
            "لا دورة مياه في دور الدخول",
            f"ADM Vol 1 {brief.access_standard} para 2.19", entrance,
            (), "0", "≥ 1",
        )


def r_adm_corridor_width(layout: Layout, brief: Brief) -> Iterable[Violation]:
    min_w = P.corridor_min_width[brief.access_standard]
    for s in layout.storeys:
        for r in s.rooms:
            if r.type not in CIRCULATION or r.type is RoomType.STAIR:
                continue
            if r.r.min_dim < min_w:
                yield Violation(
                    "ADM-002", Severity.ERROR,
                    "عرض ممر/ردهة الحركة دون الحد",
                    f"ADM Vol 1 {brief.access_standard} Table 2",
                    s.index, (r.id,), fmt_m(r.r.min_dim), fmt_m(min_w),
                )


def r_adm_door_widths(layout: Layout, brief: Brief) -> Iterable[Violation]:
    min_w = _door(brief)
    for s in layout.storeys:
        for o in s.openings:
            if o.kind not in DOOR_KINDS:
                continue
            if o.clear_width_mm < min_w:
                yield Violation(
                    "ADM-001", Severity.ERROR,
                    f"خلوص فتحة الباب {o.id} دون الحد",
                    f"ADM Vol 1 {brief.access_standard} Table 2",
                    s.index, o.rooms(),
                    f"{o.clear_width_mm} مم", f"{min_w} مم",
                )


def r_adm_door_nibs(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    الجدار المشترك يستوعب الباب مع كتفَيه.

    فحص على خطوط المراكز يمنع بابًا مستحيلًا قبل أن يصل إلى
    `placement.py`، حيث يفشل حلّه ويظهر كـ`DRW-000` غامض.
    """
    nib = P.door_side_nib
    min_w = _door(brief)
    for s in layout.storeys:
        by_id = {r.id: r for r in s.rooms}
        for o in s.openings:
            if o.kind not in DOOR_KINDS or o.b is None:
                continue
            if o.a not in by_id or o.b not in by_id:
                continue
            shared, _ = by_id[o.a].r.shared_edge(by_id[o.b].r)
            need = max(o.clear_width_mm, min_w) + 2 * nib
            if shared < need:
                yield Violation(
                    "ADM-004", Severity.ERROR,
                    f"الجدار المشترك لا يستوعب الباب {o.id} مع كتفَيه",
                    f"ADM Vol 1 {brief.access_standard} — approach to doors",
                    s.index, o.rooms(), fmt_m(shared), fmt_m(need),
                )


# ═══════════════════════ Part F — التهوية ═══════════════════════

def r_adf_purge(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for s in layout.storeys:
        env = s.envelope.to_rect()
        openable: dict[str, int] = {}
        for o in s.openings:
            if o.is_external and o.kind in {
                OpeningKind.WINDOW, OpeningKind.ESCAPE_WINDOW,
                OpeningKind.DOOR,
            }:
                openable[o.a] = openable.get(o.a, 0) + o.openable_area_mm2
        for r in s.rooms:
            if r.type not in NEEDS_PURGE_VENT:
                continue
            if r.r.external_perimeter(env) <= 0:
                yield Violation(
                    "ADF-001", Severity.ERROR,
                    "غرفة تحتاج تهوية تنظيف بلا واجهة خارجية",
                    "ADF Vol 1 2021 para 1.5", s.index, (r.id,),
                    "0 واجهة", "واجهة خارجية واحدة على الأقل",
                )
                continue
            need = int(r.r.area * P.purge_vent_ratio)
            have = openable.get(r.id, 0)
            if have < need:
                yield Violation(
                    "ADF-001", Severity.ERROR,
                    "مساحة الفتح القابل للتشغيل دون النسبة المطلوبة",
                    "ADF Vol 1 2021 Table 1.3", s.index, (r.id,),
                    fmt_area(have), fmt_area(need),
                )


def r_adf_extract(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    الشفط الميكانيكي. لا نُنمذج المجاري، فالحكم تحذير لا خطأ: غرفة رطبة
    داخلية ممكنة تنفيذيًا بمجرى مُعتمد، وتقديرُ ذلك للمهندس.
    """
    for s in layout.storeys:
        env = s.envelope.to_rect()
        for r in s.rooms:
            if r.type not in NEEDS_EXTRACT:
                continue
            rate = P.extract_rates_ls.get(r.type)
            if rate is None:
                continue
            if r.r.external_perimeter(env) <= 0:
                yield Violation(
                    "ADF-002", Severity.WARN,
                    f"غرفة رطبة داخلية تحتاج شفطًا {rate} ل/ث — "
                    f"يلزم مسار مجرى مُعتمد (غير مُنمذَج)",
                    "ADF Vol 1 2021 Table 1.1", s.index, (r.id,),
                    "بلا واجهة", f"{rate} ل/ث",
                )


# ═══════════════════════ Part B — الحريق ═══════════════════════

def r_adb_protected_stair(layout: Layout, brief: Brief) -> Iterable[Violation]:
    top = brief.top_floor_level_mm
    if top <= P.protected_stair_threshold:
        return
    for s in layout.storeys:
        stairs = [r for r in s.rooms if r.type in STAIR_TYPES]
        if not stairs:
            continue
        if not s.protected_stair:
            yield Violation(
                "ADB-001", Severity.ERROR,
                "أعلى أرضية فوق الحد يلزمها سلّم محمي — لم يُعلَن",
                "ADB Vol 1 2019 para 2.5", s.index,
                tuple(r.id for r in stairs),
                fmt_m(top), f"> {fmt_m(P.protected_stair_threshold)}",
            )


def r_adb_fire_doors(layout: Layout, brief: Brief) -> Iterable[Violation]:
    label = f"FD{P.fire_rating_minutes_int}"
    for s in layout.storeys:
        if not s.protected_stair:
            continue
        stair_ids = {r.id for r in s.rooms if r.type in STAIR_TYPES}
        if not stair_ids:
            continue
        by_id = {r.id: r for r in s.rooms}
        declared = {
            frozenset({o.a, o.b}): o.kind for o in s.openings if o.b
        }
        g = access_graph(s, _door(brief))
        for sid in sorted(stair_ids):
            for nb in sorted(g.get(sid, ())):
                if by_id[nb].type in CIRCULATION:
                    continue
                kind = declared.get(frozenset({sid, nb}))
                if kind is not OpeningKind.FIRE_DOOR:
                    yield Violation(
                        "ADB-003", Severity.ERROR,
                        f"السلّم المحمي مفتوح على غرفة بلا باب مقاوم {label}",
                        "ADB Vol 1 2019 para 2.6 / Appendix C",
                        s.index, (sid, nb),
                        str(kind or "بلا باب"), label,
                    )


def r_adb_alt_escape(layout: Layout, brief: Brief) -> Iterable[Violation]:
    top = brief.top_floor_level_mm
    if top > P.alt_escape_threshold:
        yield Violation(
            "ADB-004", Severity.WARN,
            "أعلى أرضية فوق الحد: يلزم مخرج بديل من كل دور علوي أو نظام "
            "رشاشات — غير مُنمذَج في هذا النظام",
            "ADB Vol 1 2019 para 2.7–2.9", None, (),
            fmt_m(top), f"> {fmt_m(P.alt_escape_threshold)}",
        )


def r_adb_escape_windows(layout: Layout, brief: Brief) -> Iterable[Violation]:
    """
    غرف السكن في الأدوار العلوية دون حد السلّم المحمي تحتاج نافذة هروب.
    فوق الحد يتولّى السلّم المحمي المسار، فلا تُطلب النافذة.
    """
    lo, hi = P.escape_window_sill_range
    for s in layout.storeys:
        spec = brief.storey_spec(s.index)
        if spec.index == brief.entrance_storey:
            continue
        if spec.floor_level_mm > P.protected_stair_threshold:
            continue

        served = {
            o.a for o in s.openings
            if o.kind is OpeningKind.ESCAPE_WINDOW
        }
        for r in s.rooms:
            if r.type in HABITABLE and r.id not in served:
                yield Violation(
                    "ADB-005", Severity.ERROR,
                    "غرفة سكن في دور علوي بلا نافذة هروب",
                    "ADB Vol 1 2019 para 2.10", s.index, (r.id,),
                    "بلا نافذة هروب", "نافذة هروب مطابقة",
                )

        for o in s.openings:
            if o.kind is not OpeningKind.ESCAPE_WINDOW:
                continue
            if o.openable_area_mm2 < P.escape_window_min_area:
                yield Violation(
                    "ADB-002", Severity.ERROR,
                    f"نافذة الهروب {o.id}: مساحة الفتح دون الحد",
                    "ADB Vol 1 2019 para 2.10", s.index, (o.a,),
                    fmt_area(o.openable_area_mm2),
                    fmt_area(P.escape_window_min_area),
                )
            if o.clear_width_mm < P.escape_window_min_dim:
                yield Violation(
                    "ADB-002", Severity.ERROR,
                    f"نافذة الهروب {o.id}: العرض دون الحد",
                    "ADB Vol 1 2019 para 2.10", s.index, (o.a,),
                    f"{o.clear_width_mm} مم",
                    f"{P.escape_window_min_dim} مم",
                )
            if not (lo <= o.sill_mm <= hi):
                yield Violation(
                    "ADB-002", Severity.ERROR,
                    f"نافذة الهروب {o.id}: منسوب الجلسة خارج المجال",
                    "ADB Vol 1 2019 para 2.10", s.index, (o.a,),
                    f"{o.sill_mm} مم", f"{lo}–{hi} مم",
                )


def r_adb_inner_rooms(layout: Layout, brief: Brief) -> Iterable[Violation]:
    for s in layout.storeys:
        by_id = {r.id: r for r in s.rooms}
        for rid, via in inner_rooms(s, _door(brief)).items():
            rtype = by_id[rid].type
            if rtype in INNER_ROOM_ALLOWED:
                continue
            sev = Severity.ERROR if rtype in BEDROOMS else Severity.WARN
            yield Violation(
                "ADB-006", sev,
                f"غرفة داخلية غير مسموحة من النوع {rtype} "
                f"(الوصول عبر {via})",
                "ADB Vol 1 2019 para 2.6", s.index, (rid, via),
                str(rtype), "نوع مسموح كغرفة داخلية",
            )


# ═══════════════════════ Part G — النظافة ═══════════════════════

def r_adg_wc_food(layout: Layout, brief: Brief) -> Iterable[Violation]:
    if not P.wc_needs_lobby_to_kitchen:
        return
    for s in layout.storeys:
        by_id = {r.id: r for r in s.rooms}
        declared = {frozenset({o.a, o.b}) for o in s.openings if o.b}
        for link in storey_links(s, _door(brief)):
            pair = {by_id[link.a].type, by_id[link.b].type}
            if not (RoomType.WC in pair and pair & FOOD_TYPES):
                continue
            if frozenset({link.a, link.b}) in declared:
                yield Violation(
                    "ADG-001", Severity.ERROR,
                    "دورة مياه تفتح مباشرة على منطقة تحضير الطعام — "
                    "تلزم ردهة فاصلة مُهوّاة",
                    "ADG 2015 / ADF Vol 1 2021", s.index,
                    (link.a, link.b), "باب مباشر", "ردهة فاصلة",
                )


UK_RULES: list[Rule] = [
    Rule("NDSS-GIA", "الحد الأدنى للمساحة الإجمالية", "NDSS Table 1",
         r_ndss_gia, frozenset({"uk", "space"}), ("NDSS-003", "NDSS-006")),
    Rule("NDSS-BED", "مساحة وعرض غرف النوم", "NDSS para 10",
         r_ndss_bedrooms, frozenset({"uk", "space"}),
         ("NDSS-001", "NDSS-002")),
    Rule("NDSS-STO", "التخزين المدمج", "NDSS para 9",
         r_ndss_storage, frozenset({"uk", "space"}), ("NDSS-004",)),
    Rule("NDSS-CEIL", "ارتفاع السقف", "NDSS para 10",
         r_ndss_ceiling, frozenset({"uk", "space"}), ("NDSS-005",)),

    Rule("ADK-STAIR", "هندسة السلالم", "ADK para 1",
         r_adk_stairs, frozenset({"uk", "stair"}),
         ("ADK-000", "ADK-001", "ADK-002", "ADK-003", "ADK-004")),

    Rule("ADM-WC", "دورة مياه بدور الدخول", "ADM para 2.19",
         r_adm_wc_entrance_storey, frozenset({"uk", "access"}), ("ADM-003",)),
    Rule("ADM-CORR", "عرض الحركة", "ADM Table 2",
         r_adm_corridor_width, frozenset({"uk", "access"}), ("ADM-002",)),
    Rule("ADM-DOOR", "خلوص الأبواب", "ADM Table 2",
         r_adm_door_widths, frozenset({"uk", "access"}), ("ADM-001",)),
    Rule("ADM-NIB", "كتف الباب على الجدار المشترك", "ADM approach to doors",
         r_adm_door_nibs, frozenset({"uk", "access"}), ("ADM-004",)),

    Rule("ADF-PURGE", "تهوية التنظيف", "ADF Table 1.3",
         r_adf_purge, frozenset({"uk", "vent"}), ("ADF-001",)),
    Rule("ADF-EXTR", "الشفط الميكانيكي", "ADF Table 1.1",
         r_adf_extract, frozenset({"uk", "vent"}), ("ADF-002",)),

    Rule("ADB-STAIR", "السلّم المحمي", "ADB para 2.5",
         r_adb_protected_stair, frozenset({"uk", "fire"}), ("ADB-001",)),
    Rule("ADB-FD", "الأبواب المقاومة للحريق", "ADB para 2.6",
         r_adb_fire_doors, frozenset({"uk", "fire"}), ("ADB-003",)),
    Rule("ADB-ALT", "المخرج البديل", "ADB para 2.7–2.9",
         r_adb_alt_escape, frozenset({"uk", "fire"}), ("ADB-004",)),
    Rule("ADB-ESC", "نوافذ الهروب", "ADB para 2.10",
         r_adb_escape_windows, frozenset({"uk", "fire"}),
         ("ADB-002", "ADB-005")),
    Rule("ADB-INNER", "الغرف الداخلية", "ADB para 2.6",
         r_adb_inner_rooms, frozenset({"uk", "fire"}), ("ADB-006",)),

    Rule("ADG-WC", "فصل دورة المياه عن تحضير الطعام", "ADG",
         r_adg_wc_food, frozenset({"uk", "hygiene"}), ("ADG-001",)),
]
