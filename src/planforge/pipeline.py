"""
الأنبوب الكامل بحلقتَي تغذية راجعة:

  1. أبعاد دنيا مستنبطة من التجهيزات → تُضيَّق قبل التوليد.
  2. فشل تأثيث غرفة → يُشدّ حدها الأدنى ويُعاد التوليد.

لا مخطط يُسلَّم إلا وقد جاز التدقيقات الأربعة: جدوى، مراكز، صافٍ، تأثيث.

## حلقة ثالثة أُسقطت، ولماذا

كانت هنا حلقة تُقيس انكماش الجدران وتضخّم كل مستهدفات المساحة بعامل
موحّد لتعويضه. أُسقطت لأنها **عديمة الأثر بنيويًا**: مجموع مساحات غرف
الدور مقيَّد بمساحة المظروف قيدًا صلبًا في `solver/storey.py`، فضربُ كل
المستهدفات في عامل واحد يزيح كل الانحرافات معًا ولا يغيّر التوزيع
النسبي. لا يُسترجَع 7% انكماش من مظروف ثابت.

وكانت لها ضرر: التضخيم يرفع الحدود الدنيا الصلبة، فيقرّب التعذّر ويجعل
`generate` يُخرج قائمة فارغة عن متطلب كان قابلًا للحل.

ما بقي محلّه: `shrink_notes` تقيس الانكماش وتُبلّغه بالغرفة والرقم
المطلوب، فيرفع مؤلِّف المتطلب مستهدف **الغرفة المعنيّة** — وهو القرار
الذي لا يملك النظام معلومةً تتّخذه بدلًا منه: أي غرفة تُكبَّر وأيها
تُصغَّر تفضيلٌ تصميمي لا حساب.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from planforge.drawing.build import build_drawing
from planforge.drawing.model import Drawing
from planforge.fixtures.result import FixtureOutcome, MinEnvelope
from planforge.model.brief import Brief
from planforge.model.layout import Layout
from planforge.ranking import Features, RankWeights, extract, score
from planforge.rules.core import ComplianceReport
from planforge.rules.drawing_rules import check_drawing
from planforge.rules.fixture_rules import check_fixtures
from planforge.solver.config import SolverConfig
from planforge.solver.generate import generate
from planforge.units import area_m2

MAX_ROUNDS = 3
TIGHTEN_SLACK = 1.02
SHRINK_REPORT_THRESHOLD = 0.03


@dataclass
class Result:
    layout: Layout
    drawing: Drawing
    layout_report: ComplianceReport
    drawing_report: ComplianceReport
    fixture_report: ComplianceReport
    fixtures: FixtureOutcome
    features: Features
    rank: float
    rounds: int
    shrink_ratio: float
    """متوسط (المساحة الصافية ÷ مساحة خط المركز). 0.93 يعني انكماش 7%."""
    shrink_notes: list[str] = field(default_factory=list)
    variation: int = 0

    @property
    def ok(self) -> bool:
        return all(
            rep.ok for rep in (
                self.layout_report, self.drawing_report, self.fixture_report
            )
        )

    @property
    def total_errors(self) -> int:
        return sum(
            len(rep.errors) for rep in (
                self.layout_report, self.drawing_report, self.fixture_report
            )
        )

    @property
    def total_warnings(self) -> int:
        return sum(
            len(rep.warnings) for rep in (
                self.layout_report, self.drawing_report, self.fixture_report
            )
        )


def _apply_min_dims(
    brief: Brief, derived: dict[str, MinEnvelope], slack: float = 1.0
) -> Brief:
    """رفع الحد الأدنى للعرض والمساحة إلى ما تفرضه التجهيزات."""
    rooms = []
    for r in brief.rooms:
        env = derived.get(r.id)
        if env is None or not env.ok:
            rooms.append(r)
            continue
        mw = int(env.min_dim * slack)
        ma = int(env.area * slack)
        rooms.append(r.model_copy(update={
            "min_width_mm": max(r.min_width_mm or 0, mw),
            "min_area_mm2": max(r.min_area_mm2 or 0, ma),
            "target_area_mm2": max(r.target_area_mm2, ma),
        }))
    return brief.model_copy(update={"rooms": tuple(rooms)})


def _shrink(dwg: Drawing) -> float:
    ratios = [
        r.shrink_ratio
        for st in dwg.storeys for r in st.rooms
        if r.centerline_area_mm2 > 0 and r.shrink_ratio > 0
    ]
    return sum(ratios) / len(ratios) if ratios else 1.0


def shrink_notes(dwg: Drawing, brief: Brief) -> list[str]:
    """
    الغرف التي انكمشت دون مستهدفها، مع المستهدف المطلوب على خط المركز.

    قابل للتصرّف مباشرة: الرقم المُخرَج هو ما يُكتب في المتطلب. بلا هذا
    يقرأ المستخدم `DRW-001` ولا يعرف كم يرفع.
    """
    targets = {
        r.id: r.target_area_mm2 for r in brief.rooms if r.target_area_mm2
    }
    out: list[str] = []
    for st in dwg.storeys:
        for r in st.rooms:
            want = targets.get(r.id)
            if not want or r.area >= want:
                continue
            loss = (want - r.area) / want
            if loss < SHRINK_REPORT_THRESHOLD:
                continue
            need = int(want / max(r.shrink_ratio, 0.5))
            out.append(
                f"{r.id}: صافٍ {area_m2(r.area):.2f} م² دون مستهدف "
                f"{area_m2(want):.2f} م² ({loss:.0%} انكماش) — "
                f"ارفع المستهدف إلى {area_m2(need):.2f} م²"
            )
    return out


def run(
    brief: Brief,
    cfg: SolverConfig | None = None,
    *,
    arabic_labels: bool = True,
    weights: RankWeights | None = None,
    skip_fixtures: bool = False,
) -> tuple[Result | None, ComplianceReport, list[Result]]:
    """
    يُعيد (أفضل نتيجة جائزة، تقرير الجدوى، كل ما فُحص).

    `None` تعني أن أيًّا من البدائل لم يجُز التدقيقات — والقائمة الثالثة
    تحمل أقربها، فيُعرض على المهندس بدل إخفائه.
    """
    cfg = cfg or SolverConfig(seed=brief.seed)
    weights = weights or RankWeights()

    base = brief
    if not skip_fixtures:
        from planforge.fixtures.build import derive_min_dimensions
        derived = derive_min_dimensions(
            brief, deterministic=cfg.deterministic
        )
        if derived:
            base = _apply_min_dims(brief, derived)

    tightened: dict[str, MinEnvelope] = {}
    attempted: list[Result] = []
    feas: ComplianceReport | None = None

    for round_no in range(1, MAX_ROUNDS + 1):
        working = base
        if tightened:
            working = _apply_min_dims(
                working, tightened, slack=TIGHTEN_SLACK
            )

        cands, feas = generate(working, cfg)
        if not feas.ok or not cands:
            break

        round_results: list[Result] = []
        grew = False

        for cand in cands:
            dwg, problems = build_drawing(
                cand.layout, brief, arabic_labels=arabic_labels
            )
            drep = check_drawing(dwg, brief, problems)

            if skip_fixtures:
                fout = FixtureOutcome.empty()
            else:
                from planforge.fixtures.build import furnish
                fout = furnish(dwg, brief, deterministic=cfg.deterministic)
            frep = check_fixtures(dwg, brief, fout)

            feats = extract(
                dwg, brief, cand.report, drep, frep, fout.kitchens
            )
            res = Result(
                layout=cand.layout, drawing=dwg,
                layout_report=cand.report, drawing_report=drep,
                fixture_report=frep, fixtures=fout, features=feats,
                rank=score(feats, weights), rounds=round_no,
                shrink_ratio=round(_shrink(dwg), 4),
                shrink_notes=shrink_notes(dwg, brief),
                variation=cand.variation,
            )
            attempted.append(res)
            round_results.append(res)

            # الحلقة 2: كل غرفة تعذّر تأثيثها تشدّ حدها الأدنى
            for rid, env in fout.unfurnishable.items():
                prev = tightened.get(rid)
                if prev is None or env.area > prev.area:
                    tightened[rid] = env
                    grew = True

        passing = [r for r in round_results if r.ok]
        if passing:
            passing.sort(key=lambda r: (-r.rank, r.variation))
            return passing[0], feas, attempted

        if not grew:
            break        # لا جديد يُشدّ: إعادة المحاولة تُعيد النتيجة نفسها

    return None, feas or ComplianceReport(brief.project_name), attempted


def closest(attempted: list[Result]) -> Result | None:
    """أقرب بديل إلى الجواز — يُعرض عند فشل كل البدائل."""
    if not attempted:
        return None
    return min(
        attempted,
        key=lambda r: (r.total_errors, r.total_warnings, -r.rank),
    )
