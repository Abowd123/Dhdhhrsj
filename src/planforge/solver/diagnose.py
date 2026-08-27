"""
تشخيص تعذّر التبليط: من INFEASIBLE إلى سبب مرقَّم باقتراح عددي.

المشكلة: `solve_storey` تُعيد None. لا شيء أكثر. والمستخدم أمام متطلب
من ثلاثين حقلًا لا يعرف أيّها المُلزِم.

طبقتان:
  1. فحوص حسابية بلا مُحلّل — فورية، وتكشف أغلب الحالات لأن أشهر سبب
     للتعذّر حسابي محض: مجموع المساحات لا يساوي المظروف.
  2. سُلَّم إرخاء — يُشغَّل المُحلّل مع تخفيف مجموعة قيود واحدة في كل
     درجة، وأول درجة تنجح تُسمّي القيد المُلزِم.

⚠ السُّلَّم ليس أصغر مجموعة متعذّرة رياضيًا (IIS). ترتيب الدرجات
افتراضي مبني على ما أرجّح، وقد يكون القيد الحقيقي أدنى في السُّلَّم
فيُنسب التعذّر إلى درجة أعلى. المخرج يصرّح بهذا.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any, Iterable
from planforge.codes.uk.profile import UK
from planforge.geometry.rect import Rect
from planforge.model.brief import Brief, RoomRequirement
from planforge.solver.storey import (
    SPINE_TYPES, StoreyRequest, StoreySolution, solve_storey,
)
from planforge.units import area_m2

BALANCE_TOL = 0.02          # 2% — يستوعب تقريب الشبكة لا خطأً حسابيًا
ABSOLUTE_FLOOR_MM = 700     # أضيق ما يُقبل هندسيًا في أي إرخاء
RUNG_TIME_CAP_S = 12.0


# ─────────────────────── النتائج ───────────────────────

@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str            # "blocking" | "likely" | "note"
    message: str
    suggestion: str = ""
    storey: int | None = None
    rooms: tuple[str, ...] = ()

    def line(self) -> str:
        where = f"دور {self.storey}: " if self.storey is not None else ""
        return f"[{self.code}] {where}{self.message}"


@dataclass
class Diagnosis:
    findings: list[Finding]
    solved: dict[int, bool]              # أي دور حُلّ كما هو
    binding: dict[int, str]              # دور → اسم درجة الإرخاء المُنجحة
    unresolved: tuple[int, ...] = ()     # أدوار لم تُحلّ حتى بكل الإرخاء

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "blocking"]

    @property
    def ok(self) -> bool:
        if not self.blocking and not self.solved:
            return True      # لم يُشغَّل المُحلّل: لا مانع معروف
        return (
            bool(self.solved)
            and all(self.solved.values())
            and not self.blocking
        )


# ─────────────────────── قراءة متحفّظة ───────────────────────

def _g(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _floor_of(req: RoomRequirement) -> int:
    return max(
        UK.practical_min_width.get(req.type, ABSOLUTE_FLOOR_MM),
        req.min_width_mm or 0,
    )


def _area_window(req: RoomRequirement) -> tuple[int, int]:
    lo = req.min_area_mm2 or int(req.target_area_mm2 * 0.85)
    hi = req.max_area_mm2 or int(req.target_area_mm2 * 1.45)
    return (min(lo, req.target_area_mm2), max(hi, req.target_area_mm2))


def _mutate(req: RoomRequirement, **changes: Any) -> RoomRequirement:
    return req.model_copy(update=changes)


def _by_storey(brief: Brief) -> dict[int, list[RoomRequirement]]:
    out: dict[int, list[RoomRequirement]] = {
        i: [] for i in range(brief.n_storeys)
    }
    for r in brief.rooms:
        idx = r.storey if r.storey is not None else brief.entrance_storey
        out.setdefault(idx, []).append(r)
    return out


# ═══════════════ الطبقة 1: فحوص حسابية ═══════════════

def analytic_findings(brief: Brief, cfg: Any) -> list[Finding]:
    env = brief.build_envelope
    grid = _g(cfg, "grid_mm", 100)
    min_band = _g(cfg, "min_band_mm", 1800)
    min_spine = _g(cfg, "min_spine_mm", 1000)
    max_bands = _g(cfg, "max_bands_per_zone", 4)
    out: list[Finding] = []

    if env.w <= 0 or env.h <= 0:
        out.append(Finding(
            "ENVELOPE-EMPTY", "blocking",
            f"الارتدادات تفني القطعة: المظروف {env.w}×{env.h} مم",
            "اخفض الارتدادات أو كبّر القطعة",
        ))
        return out

    floating = [r.id for r in brief.rooms if r.storey is None]
    if floating and brief.is_multi_storey:
        out.append(Finding(
            "STOREY-UNASSIGNED", "blocking",
            f"{len(floating)} غرفة بلا دور محدّد — لا موزّع تلقائي في هذا "
            f"الإصدار",
            "ثبّت storey لكل غرفة؛ التشخيص أدناه ينسبها إلى دور الدخول",
            rooms=tuple(sorted(floating)[:8]),
        ))

    per = _by_storey(brief)
    for storey, rooms in sorted(per.items()):
        if not rooms:
            out.append(Finding(
                "STOREY-EMPTY", "blocking", "دور بلا غرف",
                "أضف غرفًا أو اخفض storeys", storey=storey,
            ))
            continue

        # ── توازن المساحات: يُقاس على الحدود الصلبة لا على المستهدفات ──
        #
        # المستهدف قيد ناعم (minimize)، والصلب هو min_area/max_area. نفس
        # المنطق في rules/brief_rules.py — وإلا تعارض check-brief وdiagnose.
        lo_sum = sum(_area_window(r)[0] for r in rooms)
        hi_sum = sum(_area_window(r)[1] for r in rooms)

        if lo_sum > env.area:
            out.append(Finding(
                "AREA-BALANCE", "blocking",
                f"مجموع الحدود الدنيا {area_m2(lo_sum):.2f} م² يفيض عن "
                f"مظروف {area_m2(env.area):.2f} م² — لا تبليط ممكن",
                "اخفض min_area_mm2 لبعض الغرف أو كبّر المظروف",
                storey=storey,
            ))
        elif hi_sum < env.area:
            gap = env.area - hi_sum
            out.append(Finding(
                "AREA-BALANCE", "blocking",
                f"مجموع السقوف {area_m2(hi_sum):.2f} م² لا يملأ مظروف "
                f"{area_m2(env.area):.2f} م² — التبليط تام فلا فراغ",
                f"ارفع max_area_mm2 أو أضف {area_m2(gap):.2f} م² "
                f"({gap:,} مم²)",
                storey=storey,
            ))
        else:
            total = sum(r.target_area_mm2 for r in rooms)
            drift = (total - env.area) / env.area
            if abs(drift) > BALANCE_TOL:
                gap = env.area - total
                verb = "أضف" if gap > 0 else "اخفض"
                out.append(Finding(
                    "AREA-BALANCE", "note",
                    f"مجموع المستهدفات {area_m2(total):.2f} م² ضد مظروف "
                    f"{area_m2(env.area):.2f} م² — انحراف {drift:+.1%}",
                    f"{verb} {area_m2(abs(gap)):.2f} م² ({abs(gap):,} مم²) "
                    f"إن أردت الغرف عند مستهدفها بالضبط.",
                    storey=storey,
                ))

        # ── أرقام مستحيلة هندسيًا ──
        for r in rooms:
            floor = _floor_of(r)
            lo, hi = _area_window(r)

            if floor > min(env.w, env.h):
                out.append(Finding(
                    "ROOM-WIDER-THAN-PLOT", "blocking",
                    f"{r.id}: أقل عرض {floor} مم يتجاوز أصغر بعد للمظروف "
                    f"({min(env.w, env.h)} مم)",
                    "كبّر القطعة أو خفّض min_width_mm",
                    storey=storey, rooms=(r.id,),
                ))
            if floor * floor > hi:
                out.append(Finding(
                    "ROOM-FLOOR-VS-AREA", "blocking",
                    f"{r.id}: أقل عرض {floor} مم يقتضي "
                    f"{area_m2(floor * floor):.2f} م² على الأقل، وسقف "
                    f"مساحته {area_m2(hi):.2f} م²",
                    f"ارفع المستهدف إلى {area_m2(floor * floor):.2f} م² "
                    f"أو أزل max_area_mm2",
                    storey=storey, rooms=(r.id,),
                ))
            if lo > hi:
                out.append(Finding(
                    "AREA-WINDOW-INVERTED", "blocking",
                    f"{r.id}: min_area ({area_m2(lo):.2f}) أكبر من max_area "
                    f"({area_m2(hi):.2f})",
                    "صحّح الحدّين", storey=storey, rooms=(r.id,),
                ))

            # الغرفة في شريط: عرضها = عرض الشريط ≥ min_band، وارتفاعها
            # ≥ floor. فمساحتها لا تقلّ عن حاصلهما.
            need = min_band * max(floor, ABSOLUTE_FLOOR_MM)
            if r.type not in SPINE_TYPES and hi < need:
                out.append(Finding(
                    "ROOM-VS-MIN-BAND", "likely",
                    f"{r.id}: سقف مساحته {area_m2(hi):.2f} م² دون ما يفرضه "
                    f"أضيق شريط ({min_band} × {max(floor, ABSOLUTE_FLOOR_MM)} "
                    f"مم = {area_m2(need):.2f} م²)",
                    f"ارفع المستهدف إلى {area_m2(need):.2f} م² أو اخفض "
                    f"min_band_mm إلى "
                    f"{max(900, hi // max(floor, ABSOLUTE_FLOOR_MM))} مم",
                    storey=storey, rooms=(r.id,),
                ))

        # ── شريط الحركة: مساحته ÷ عرض المظروف = ارتفاعه ──
        spine = [r for r in rooms if r.type in SPINE_TYPES]
        if not spine:
            out.append(Finding(
                "NO-CIRCULATION", "likely",
                "لا غرفة حركة في هذا الدور",
                "أضف hall أو landing — بدونها يفشل ربط الأبواب في الصقل "
                "حتى لو نجح التبليط",
                storey=storey,
            ))
        for r in spine:
            band = r.target_area_mm2 / env.w
            if band < min_spine:
                out.append(Finding(
                    "SPINE-TOO-THIN", "blocking",
                    f"{r.id}: شريط حركة بعرض المظروف ⟹ ارتفاعه "
                    f"{band:.0f} مم، والحدّ {min_spine} مم",
                    f"ارفع المستهدف إلى {area_m2(env.w * min_spine):.2f} م² "
                    f"({env.w * min_spine:,} مم²)",
                    storey=storey, rooms=(r.id,),
                ))
            elif band > env.h * 0.45:
                out.append(Finding(
                    "SPINE-TOO-FAT", "note",
                    f"{r.id}: شريط الحركة يستهلك "
                    f"{band / env.h * 100:.0f}% من العمق",
                    "اخفض مستهدفه — الحركة مساحة مهدورة تُقاس في الترتيب",
                    storey=storey, rooms=(r.id,),
                ))

        # ── سعة الأشرطة ──
        placed = [r for r in rooms if r.type not in SPINE_TYPES]
        capacity = 2 * max_bands
        if len(placed) > capacity:
            out.append(Finding(
                "BANDS-TOO-FEW", "likely",
                f"{len(placed)} غرفة غير حركية على سعة {capacity} شريطًا "
                f"(منطقتان × {max_bands})",
                f"ارفع max_bands_per_zone إلى "
                f"{math.ceil(len(placed) / 2)} أو انقل غرفًا إلى دور آخر",
                storey=storey,
            ))
        if min_band * 2 > env.w:
            out.append(Finding(
                "BAND-MIN-VS-WIDTH", "blocking",
                f"شريطان بحدّ {min_band} مم يحتاجان {min_band * 2} مم "
                f"وعرض المظروف {env.w} مم",
                f"اخفض min_band_mm إلى {env.w // 2} مم",
                storey=storey,
            ))

    if env.w % grid or env.h % grid:
        out.append(Finding(
            "GRID-REMAINDER", "note",
            f"المظروف {env.w}×{env.h} مم غير قابل للقسمة على شبكة {grid} مم",
            "المُحلّل يُلحق الباقي بآخر حدّ فيبقى التبليط تامًا — "
            "تنبيه لا خطأ",
        ))
    return out


# ═══════════════ الطبقة 2: سُلَّم الإرخاء ═══════════════

@dataclass(frozen=True, slots=True)
class Rung:
    name: str
    label: str
    fix: str


LADDER: tuple[Rung, ...] = (
    Rung("aspect", "سقف النسبة الباعية",
         "ارفع max_aspect للغرف المعنية أو max_aspect_default"),
    Rung("area_window", "مجال المساحة (min_area / max_area)",
         "وسّع المجال أو أزل الحدّين واتركهما للمستهدف"),
    Rung("min_dims", "أقل عرض للغرف (practical_min_width)",
         "أرقام العرف المهني أضيق مما يسمح به هذا المتطلب — "
         "خفّضها أو كبّر الغرف"),
    Rung("band_min", "أضيق شريط (min_band_mm)",
         "اخفض min_band_mm في SolverConfig إلى 1500 أو 1200"),
    Rung("band_count", "عدد الأشرطة (max_bands_per_zone)",
         "ارفع max_bands_per_zone إلى 5 أو 6"),
    Rung("no_spine", "إلزام شريط الحركة",
         "مستهدف غرفة الحركة لا يتناسب مع عرض المظروف — "
         "أعد حسابه أو ألغِ require_spine"),
    Rung("all", "كل ما سبق مجتمعًا",
         "التعذّر بنيوي: أعد توزيع الغرف على الأدوار أو غيّر أبعاد القطعة"),
)


def _relaxed_rooms(
    rooms: Iterable[RoomRequirement], rung: str
) -> tuple[RoomRequirement, ...]:
    out: list[RoomRequirement] = []
    for r in rooms:
        ch: dict[str, Any] = {}
        if rung in ("aspect", "all"):
            ch["max_aspect"] = 100.0
        if rung in ("area_window", "all"):
            ch["min_area_mm2"] = int(r.target_area_mm2 * 0.40)
            ch["max_area_mm2"] = int(r.target_area_mm2 * 2.60)
        if rung in ("min_dims", "all"):
            ch["min_width_mm"] = ABSOLUTE_FLOOR_MM
        out.append(_mutate(r, **ch) if ch else r)
    return tuple(out)


class _Cfg:
    """غلاف يسمح بتخفيف حقول الإعداد بلا مسّ الأصل."""

    def __init__(self, base: Any, **over: Any) -> None:
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_over", over)

    def __getattr__(self, name: str) -> Any:
        over = object.__getattribute__(self, "_over")
        if name in over:
            return over[name]
        return getattr(object.__getattribute__(self, "_base"), name)


def _try(
    storey: int,
    env: Rect,
    rooms: list[RoomRequirement],
    cfg: Any,
    rung: str,
) -> StoreySolution | None:
    over: dict[str, Any] = {
        "time_limit_s": min(_g(cfg, "time_limit_s", 20.0), RUNG_TIME_CAP_S)
    }
    if rung in ("band_min", "all"):
        over["min_band_mm"] = 900
    if rung in ("band_count", "all"):
        over["max_bands_per_zone"] = 6
    req = StoreyRequest(
        index=storey, envelope=env,
        rooms=_relaxed_rooms(rooms, rung),
        require_spine=rung not in ("no_spine", "all"),
    )
    return solve_storey(req, _Cfg(cfg, **over))


def relaxation_findings(
    brief: Brief, cfg: Any, *, storeys: Iterable[int] | None = None
) -> tuple[list[Finding], dict[int, bool], dict[int, str], list[int]]:
    env = brief.build_envelope
    per = _by_storey(brief)
    targets = sorted(per) if storeys is None else sorted(storeys)

    findings: list[Finding] = []
    solved: dict[int, bool] = {}
    binding: dict[int, str] = {}
    unresolved: list[int] = []

    for storey in targets:
        rooms = per.get(storey, [])
        if not rooms:
            solved[storey] = False
            unresolved.append(storey)
            continue

        base = StoreyRequest(
            index=storey, envelope=env, rooms=tuple(rooms)
        )
        base_cfg = _Cfg(
            cfg,
            time_limit_s=min(_g(cfg, "time_limit_s", 20.0), 15.0),
        )
        if solve_storey(base, base_cfg) is not None:
            solved[storey] = True
            continue

        solved[storey] = False
        hit: Rung | None = None
        for rung in LADDER:
            if _try(storey, env, rooms, cfg, rung.name) is not None:
                hit = rung
                break

        if hit is None:
            unresolved.append(storey)
            findings.append(Finding(
                "UNRESOLVED", "blocking",
                "متعذّر حتى بإرخاء كل مجموعات القيود",
                "السبب ليس رقمًا واحدًا: راجع التوازن الحسابي أعلاه، "
                "ثم أعد توزيع الغرف على الأدوار",
                storey=storey,
            ))
            continue

        binding[storey] = hit.name
        findings.append(Finding(
            f"BINDING-{hit.name.upper()}", "blocking",
            f"القيد المُلزِم على الأرجح: {hit.label} — "
            f"الحل يظهر بإرخائه وحده",
            hit.fix, storey=storey,
        ))
    return findings, solved, binding, unresolved


# ═══════════════ المدخل ═══════════════

def diagnose(
    brief: Brief, cfg: Any, *, run_solver: bool = True
) -> Diagnosis:
    """
    التشخيص الكامل.

    `run_solver=False` يقتصر على الفحوص الحسابية — فوري، ويكفي في أغلب
    الحالات لأن أشهر سبب حسابي. السُّلَّم يستدعي المُحلّل حتى سبع مرات
    لكل دور، فأسوأ حالة لثلاثة أدوار نحو أربع دقائق.
    """
    findings = analytic_findings(brief, cfg)
    if not run_solver:
        return Diagnosis(findings, {}, {})

    if any(f.severity == "blocking" for f in findings):
        findings.append(Finding(
            "SOLVER-SKIPPED", "note",
            "لم يُشغَّل المُحلّل: يوجد سبب حاجب حسابي",
            "أصلح ما فوق ثم أعد التشخيص لسُلَّم الإرخاء",
        ))
        return Diagnosis(findings, {}, {})

    extra, solved, binding, unresolved = relaxation_findings(brief, cfg)
    return Diagnosis(
        findings + extra, solved, binding, tuple(unresolved)
    )
