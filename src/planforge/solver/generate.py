"""
المُنسِّق: من Brief إلى بدائل مخططات مُدقَّقة.

مؤلَّف من الصفر في هذه الدفعة. النسخة الأصلية بُنيت على تصميم مُحلّل
سابق (`SlotSpec` + `assign_storeys` + `dim_table`) أُلغي لصالح شجرة
القطع، ولم تكن قابلة للتوفيق مع التوقيع الجديد.

المسؤولية محدودة قصدًا:
  1. فحص الجدوى — يُوقف كل شيء إن سقط.
  2. بناء `StoreyRequest` لكل دور من غرف المتطلب المثبَّتة عليه.
  3. تشغيل المُحلّل بعددٍ من التنويعات، وإسقاط المكرَّر بعد الصقل.
  4. الصقل ثم التدقيق على خطوط المراكز.

ما لا يفعله، وهو قدرة مفقودة عمّا وُصف سابقًا: **لا يوزّع الغرف على
الأدوار.** كل غرفة في متطلب متعدد الأدوار يجب أن تحمل `storey` صريحًا،
و`FEAS-001` يرفض غير ذلك برسالة واضحة بدل `INFEASIBLE` غامض.
"""
from __future__ import annotations
from dataclasses import dataclass
from planforge.codes.uk.profile import UK
from planforge.model.brief import Brief, RoomRequirement
from planforge.model.layout import Layout
from planforge.rules.brief_rules import check_brief
from planforge.rules.core import ComplianceReport, Severity, Violation
from planforge.rules.registry import default_registry
from planforge.solver.config import SolverConfig
from planforge.solver.refine import refine
from planforge.solver.storey import StoreyRequest, StoreySolution, solve_storey

ENGINE_VERSION = "0.7.0"

ERROR_PENALTY = 10 ** 7
WARN_PENALTY = 5_000


@dataclass
class Candidate:
    layout: Layout
    report: ComplianceReport
    objective: int
    variation: int
    rank_score: float
    solver_notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.report.ok


def _storey_of(brief: Brief, room: RoomRequirement) -> int:
    return room.storey if room.storey is not None else brief.entrance_storey


def _protected(brief: Brief) -> bool:
    return (
        brief.is_multi_storey
        and brief.top_floor_level_mm > UK.protected_stair_threshold
    )


def build_requests(brief: Brief) -> dict[int, StoreyRequest]:
    """
    طلب واحد لكل دور. المظروف هو `build_envelope` نفسه في كل الأدوار —
    المظاريف المتدرّجة تحتاج تعميم `Rect` إلى مضلّع، وهو محصور في
    `geometry/`.
    """
    env = brief.build_envelope
    protected = _protected(brief)
    out: dict[int, StoreyRequest] = {}
    for spec in sorted(brief.storeys, key=lambda s: s.index):
        rooms = tuple(
            r for r in brief.rooms if _storey_of(brief, r) == spec.index
        )
        out[spec.index] = StoreyRequest(
            index=spec.index, envelope=env, rooms=rooms,
            protected_stair=protected, require_spine=True,
        )
    return out


def _solve_all(
    reqs: dict[int, StoreyRequest], cfg: SolverConfig, variation: int
) -> list[StoreySolution] | None:
    sols: list[StoreySolution] = []
    for idx in sorted(reqs):
        sol = solve_storey(reqs[idx], cfg, variation=variation)
        if sol is None:
            return None
        sols.append(sol)
    return sols


def _signature(layout: Layout) -> frozenset:
    return frozenset(
        (st.index, r.id, r.rect.x, r.rect.y, r.rect.w, r.rect.h)
        for st in layout.storeys for r in st.rooms
    )


def generate(
    brief: Brief, cfg: SolverConfig | None = None
) -> tuple[list[Candidate], ComplianceReport]:
    """
    يُعيد (البدائل مرتَّبة، تقرير الجدوى).

    قائمة فارغة مع تقرير مُجدٍ تعني أن المُحلّل تعذّر — شغّل
    `planforge diagnose` ليقول أي قيد كان المُلزِم.
    """
    cfg = cfg or SolverConfig(seed=brief.seed)
    feas = check_brief(brief, cfg)
    if not feas.ok:
        return [], feas

    reqs = build_requests(brief)
    protected = _protected(brief)
    registry = default_registry()

    candidates: list[Candidate] = []
    seen: set[frozenset] = set()

    for variation in range(max(1, cfg.n_alternatives)):
        sols = _solve_all(reqs, cfg, variation)
        if sols is None:
            continue

        layouts, notes = refine(sols, brief, protected_stair=protected)
        layout = Layout(
            project_name=brief.project_name,
            engine_version=ENGINE_VERSION,
            seed=cfg.seed + variation,
            storeys=layouts,
        )

        # الإسقاط بعد الصقل لا قبله: المحاذاة الرأسية قد توحّد تنويعين
        sig = _signature(layout)
        if sig in seen:
            continue
        seen.add(sig)

        report = registry.run(layout, brief)
        report.rules_run.append("SOL-001")
        for note in notes:
            report.violations.append(Violation(
                "SOL-001", Severity.WARN, note,
                "تعذّر في طبقة الصقل", None, (),
            ))
        report.sort()

        objective = sum(s.objective for s in sols)
        rank = float(
            objective
            + len(report.errors) * ERROR_PENALTY
            + len(report.warnings) * WARN_PENALTY
        )
        candidates.append(Candidate(
            layout=layout, report=report, objective=objective,
            variation=variation, rank_score=rank,
            solver_notes=tuple(notes),
        ))

    candidates.sort(key=lambda c: (c.rank_score, c.variation))
    return candidates, feas
