"""
فحص جدوى المتطلب — الطبقة الأولى، قبل تشغيل المُحلّل.

الغرض: كشف المتطلب المستحيل في ملّي ثانية بدل انتظار CP-SAT حتى ينفد
وقته ويُخرج `INFEASIBLE` بلا سبب مفهوم.

القيد المحوري هنا هو **توازن المساحات**: المُحلّل يفرض تبليطًا تامًّا
لمظروف البناء، فمجموع مستهدفات كل دور يساوي مساحة المظروف ولا يقاربه.
هذا أشهر سبب للتعذّر وأسهله إصلاحًا، وكشفه حسابي محض. للتشخيص الأعمق
(سُلَّم إرخاء القيود) استخدم `planforge diagnose`.
"""
from __future__ import annotations
from typing import Any
from planforge.codes.uk.profile import UK
from planforge.enums import BEDROOMS, RoomType
from planforge.model.brief import Brief
from planforge.rules.core import ComplianceReport, Severity, Violation
from planforge.units import area_m2, fmt_area, fmt_m

BALANCE_TOL = 0.02      # 2% — يستوعب تقريب الشبكة لا خطأً حسابيًا
WC_TYPES = frozenset({
    RoomType.WC, RoomType.SHOWER_ROOM, RoomType.BATHROOM,
})
STAIR_TYPES = frozenset({RoomType.STAIR, RoomType.LANDING})

FEAS_CODES = tuple(f"FEAS-{i:03d}" for i in range(1, 13))
FEASIBILITY_CODES = FEAS_CODES


def _spine_types() -> frozenset[RoomType]:
    """
    أنواع غرف الحركة التي يُنمذجها المُحلّل شريطًا بعرض المظروف.

    يُقرأ من `solver.storey` لا يُكرَّر: تعريفان لشريط الحركة يتباعدان.
    الاستيراد داخل الدالة يُبقي `check-brief` عاملًا بلا `ortools`.
    """
    try:
        from planforge.solver.storey import SPINE_TYPES
        return SPINE_TYPES
    except ImportError:
        return frozenset({
            RoomType.ENTRANCE_HALL, RoomType.HALL,
            RoomType.LANDING, RoomType.LOBBY,
        })


def _cfg_value(cfg: Any, name: str, default: Any) -> Any:
    return getattr(cfg, name, default) if cfg is not None else default


def _area_window(req: Any) -> tuple[int, int]:
    """مجال المساحة الصلب كما يفرضه المُحلّل — لا المستهدف الناعم."""
    lo = req.min_area_mm2 or int(req.target_area_mm2 * 0.85)
    hi = req.max_area_mm2 or int(req.target_area_mm2 * 1.45)
    return (min(lo, req.target_area_mm2), max(hi, req.target_area_mm2))


def check_brief(brief: Brief, cfg: Any = None) -> ComplianceReport:
    """
    `cfg` اختياري: `SolverConfig` أو أي كائن يحمل حقولها. بدونه تُستخدم
    الافتراضات، وهي ما يستخدمه `planforge run` بلا خيارات.
    """
    rep = ComplianceReport(project_name=brief.project_name)
    rep.rules_run.extend(FEAS_CODES)
    v = rep.violations

    env = brief.build_envelope
    spine_types = _spine_types()
    min_band = _cfg_value(cfg, "min_band_mm", 1800)
    min_spine = _cfg_value(cfg, "min_spine_mm", 1000)
    max_bands = _cfg_value(cfg, "max_bands_per_zone", 4)

    # ── 1) توزيع الأدوار ──
    floating = [r.id for r in brief.rooms if r.storey is None]
    if floating and brief.is_multi_storey:
        v.append(Violation(
            "FEAS-001", Severity.ERROR,
            f"{len(floating)} غرفة بلا دور محدّد في متطلب متعدد الأدوار — "
            f"لا يوجد موزّع تلقائي، فثبّت `storey` لكل غرفة",
            "سلامة المتطلب", None, tuple(sorted(floating)[:10]),
            f"{len(floating)} بلا دور", "كل غرفة على دور",
        ))

    per_storey: dict[int, list] = {i: [] for i in range(brief.n_storeys)}
    for r in brief.rooms:
        per_storey.setdefault(
            r.storey if r.storey is not None else brief.entrance_storey, []
        ).append(r)

    for idx in sorted(per_storey):
        if not per_storey[idx]:
            v.append(Violation(
                "FEAS-002", Severity.ERROR, "دور بلا غرف",
                "سلامة المتطلب", idx, (), "0 غرفة", "≥ 1",
            ))

    # ── 2) توازن المساحات: يُقاس على الحدود الصلبة لا على المستهدفات ──
    #
    # المستهدف قيد ناعم في المُحلّل (يدخل في minimize)، والصلب هو
    # min_area/max_area. فمجموعُ مستهدفات دون المظروف قابل للحل: الغرف
    # تخرج أكبر من مستهدفها. الاستحالة الحقيقية حالتان فقط:
    #   • مجموع الحدود الدنيا يفيض عن المظروف.
    #   • مجموع السقوف لا يملأ المظروف — والتبليط تام فلا فراغ.
    for idx, rooms in sorted(per_storey.items()):
        if not rooms:
            continue
        lo_sum = sum(_area_window(r)[0] for r in rooms)
        hi_sum = sum(_area_window(r)[1] for r in rooms)

        if lo_sum > env.area:
            v.append(Violation(
                "FEAS-003", Severity.ERROR,
                "مجموع الحدود الدنيا للمساحات يفيض عن مظروف البناء — "
                "لا تبليط ممكن",
                "قيد التبليط التام", idx, (),
                fmt_area(lo_sum), f"≤ {fmt_area(env.area)}",
            ))
        elif hi_sum < env.area:
            v.append(Violation(
                "FEAS-003", Severity.ERROR,
                f"مجموع سقوف المساحات لا يملأ المظروف — التبليط تام، "
                f"فارفع السقوف أو أضف {area_m2(env.area - hi_sum):.2f} م²",
                "قيد التبليط التام", idx, (),
                fmt_area(hi_sum), f"≥ {fmt_area(env.area)}",
            ))
        else:
            total = sum(r.target_area_mm2 for r in rooms)
            drift = (total - env.area) / env.area
            if abs(drift) > BALANCE_TOL:
                gap = env.area - total
                verb = "أكبر" if gap > 0 else "أصغر"
                v.append(Violation(
                    "FEAS-003", Severity.WARN,
                    f"مجموع المستهدفات ينحرف {drift:+.1%} عن المظروف — "
                    f"الغرف ستخرج {verb} من مستهدفاتها",
                    "قيد التبليط التام", idx, (),
                    fmt_area(total), fmt_area(env.area),
                ))

    # ── 3) NDSS مقابل السعة ──
    capacity = env.area * brief.n_storeys
    required = UK.ndss_gia(
        brief.bedspaces, brief.n_bedrooms, brief.n_storeys
    )
    if required and capacity < required:
        v.append(Violation(
            "FEAS-004", Severity.ERROR,
            "سعة مظروف البناء أصغر من الحد الأدنى في NDSS، ولن تكفي بعد "
            "خصم سماكة الجدران",
            "NDSS 2015 Table 1", None, (),
            fmt_area(capacity), fmt_area(required),
        ))

    # ── 4) استحالات هندسية على مستوى الغرفة ──
    for r in brief.rooms:
        floor = max(
            r.min_width_mm or 0, UK.practical_min_width.get(r.type, 0)
        )
        if floor > env.min_dim:
            v.append(Violation(
                "FEAS-005", Severity.ERROR,
                "أضيق بعد للمظروف لا يستوعب الحد الأدنى لعرض الغرفة",
                "سلامة المتطلب", r.storey, (r.id,),
                fmt_m(env.min_dim), fmt_m(floor),
            ))
        if floor and r.target_area_mm2 < floor * floor:
            v.append(Violation(
                "FEAS-006", Severity.WARN,
                "المساحة المستهدفة أصغر من مربع الحد الأدنى للعرض",
                "سلامة المتطلب", r.storey, (r.id,),
                fmt_area(r.target_area_mm2), fmt_area(floor * floor),
            ))
        cap = r.max_area_mm2
        if cap and r.type not in spine_types:
            need = min_band * max(floor, 700)
            if cap < need:
                v.append(Violation(
                    "FEAS-012", Severity.WARN,
                    f"سقف المساحة دون ما يفرضه أضيق شريط "
                    f"({min_band} × {max(floor, 700)} مم) — "
                    f"ارفع السقف أو اخفض min_band_mm",
                    "قيد الأشرطة", r.storey, (r.id,),
                    fmt_area(cap), fmt_area(need),
                ))

    # ── 5) أسرّة مقابل الأشخاص ──
    beds = sum(
        2 if r.type in {RoomType.BEDROOM_DOUBLE, RoomType.BEDROOM_MAIN} else 1
        for r in brief.rooms if r.type in BEDROOMS
    )
    if beds < brief.bedspaces:
        v.append(Violation(
            "FEAS-007", Severity.WARN,
            "أسرّة غرف النوم أقل من عدد الأشخاص المعلَن",
            "NDSS 2015", None, (),
            f"{beds} سرير", f"{brief.bedspaces} شخص",
        ))

    # ── 6) الحركة: بلا شريط لا تُوصَل الأبواب ──
    for idx, rooms in sorted(per_storey.items()):
        if not rooms:
            continue
        spine = [r for r in rooms if r.type in spine_types]
        if not spine:
            v.append(Violation(
                "FEAS-008", Severity.ERROR,
                "لا غرفة حركة في هذا الدور — بدونها يفشل ربط الأبواب "
                "(GEO-007) حتى لو نجح التبليط",
                "سلامة الوصول", idx, (),
                "0", "≥ 1 (ردهة أو بسطة)",
            ))
        for r in spine:
            band = r.target_area_mm2 // env.w
            if band < min_spine:
                need = env.w * min_spine
                v.append(Violation(
                    "FEAS-009", Severity.ERROR,
                    f"شريط الحركة بعرض المظروف ⟹ ارتفاعه {band} مم — "
                    f"ارفع المستهدف إلى {area_m2(need):.2f} م²",
                    "قيد شريط الحركة", idx, (r.id,),
                    f"{band} مم", f"≥ {min_spine} مم",
                ))
        placed = [r for r in rooms if r.type not in spine_types]
        capacity_bands = 2 * max_bands
        if len(placed) > capacity_bands:
            v.append(Violation(
                "FEAS-010", Severity.WARN,
                f"عدد الغرف غير الحركية يتجاوز سعة الأشرطة — ارفع "
                f"max_bands_per_zone إلى {-(-len(placed) // 2)}",
                "قيد الأشرطة", idx, (),
                f"{len(placed)} غرفة", f"≤ {capacity_bands}",
            ))

    # ── 7) دورة مياه بدور الدخول ──
    if UK.wc_at_entrance_storey_required:
        ent = brief.entrance_storey
        if not any(
            r.type in WC_TYPES and r.storey in (None, ent)
            for r in brief.rooms
        ):
            v.append(Violation(
                "FEAS-011", Severity.ERROR,
                "المتطلب لا يحتوي دورة مياه قابلة للتخصيص في دور الدخول",
                f"ADM Vol 1 {brief.access_standard} para 2.19", ent,
                (), "0", "≥ 1",
            ))

    # ── 8) سلالم للأدوار المتعددة ──
    if brief.is_multi_storey:
        missing = [
            idx for idx in range(brief.n_storeys - 1)
            if not any(
                r.type is RoomType.STAIR for r in per_storey.get(idx, [])
            )
        ]
        if missing:
            v.append(Violation(
                "FEAS-002", Severity.ERROR,
                f"لا سلّم في الأدوار {missing} — لا يوجد حاقن تلقائي، "
                f"فأضف غرفة من النوع stair لكل دور دون الأعلى",
                "ADK 2013 para 1.1", None, (),
                f"{len(missing)} دور بلا سلّم", "سلّم في كل دور دون الأعلى",
            ))

    rep.sort()
    return rep
