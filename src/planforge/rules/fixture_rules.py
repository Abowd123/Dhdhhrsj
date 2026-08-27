"""
التدقيق الرابع — على قابلية التأثيث.

غرفة جازت المساحة والعرض الصافيين وسقطت هنا هي غرفة لا تُستخدم: تجوز
NDSS رقميًا ولا تستوعب طقمها هندسيًا. هذا آخر مرشّح قبل التسليم، وهو
الفحص الذي يفرّق بين مخطط صحيح ومخطط مسكون.

الأرقام التي تستند إليها هذه الطبقة أخطر ما في المشروع: لا تُقرأ في
التدقيق وحده، بل تُستنبط منها الأبعاد الدنيا التي تُغذّي المُحلّل، فرقم
خاطئ في حيّز استخدام يشوّه كل مخطط مولَّد.
"""
from __future__ import annotations
from typing import Iterable
from planforge.codes.uk.detail_profile import DETAIL
from planforge.codes.uk.fixtures_profile import FIX
from planforge.drawing.model import Drawing
from planforge.fixtures.result import FixtureOutcome
from planforge.model.brief import Brief
from planforge.rules.core import ComplianceReport, Rule, Severity, Violation
from planforge.units import fmt_area, fmt_m

DRAIN_RUN_WARN_MM = DETAIL.drain_run_warn_mm


def f_unfurnishable(
    dwg: Drawing, brief: Brief, out: FixtureOutcome
) -> Iterable[Violation]:
    for s in dwg.storeys:
        for room in s.rooms:
            need = out.unfurnishable.get(room.id)
            if need is None:
                continue
            codes = FIX.set_for(room.type)
            yield Violation(
                "FIX-001", Severity.ERROR,
                f"الغرفة لا تستوعب طقمها ({', '.join(codes)}) بحيّزات "
                f"الاستخدام ودوران الباب",
                "ADM Vol 1 (رسومات الخلوص) / BS 6465-2",
                s.index, (room.id,),
                f"{fmt_m(room.w)} × {fmt_m(room.h)} = {fmt_area(room.area)}",
                f"≥ {fmt_m(need.min_dim)} × {fmt_m(need.max_dim)} = "
                f"{fmt_area(need.area)}",
            )


def f_turning_space(
    dwg: Drawing, brief: Brief, out: FixtureOutcome
) -> Iterable[Violation]:
    """
    خلوص الدوران كفحص بعد الحدث.

    الحزم يفرضه قيدًا صلبًا، فسقوطه هناك يظهر `FIX-001`. هذه القاعدة
    تلتقط الحالة التي لا يصلها الحزم: أصغر بعد صافٍ دون قطر الدائرة، أي
    أن الغرفة مستحيلة قبل وضع أي تجهيز — ورسالتها أدقّ من «لا يمكن الحزم».
    """
    need = FIX.turning_space.get(brief.access_standard, 0)
    if not need:
        return
    for s in dwg.storeys:
        for room in s.rooms:
            if room.type not in FIX.turning_applies:
                continue
            if room.id in out.unfurnishable:
                continue        # التُقط بـFIX-001 برسالة أوضح
            if room.min_dim < need:
                yield Violation(
                    "FIX-002", Severity.ERROR,
                    "أصغر بعد صافٍ لا يستوعب خلوص الدوران",
                    f"ADM Vol 1 {brief.access_standard}", s.index,
                    (room.id,), fmt_m(room.min_dim), fmt_m(need),
                )


def f_kitchen(
    dwg: Drawing, brief: Brief, out: FixtureOutcome
) -> Iterable[Violation]:
    for s in dwg.storeys:
        ids = {r.id for r in s.rooms}
        for rid, audit in sorted(out.kitchens.items()):
            if rid not in ids:
                continue
            for message, is_error in audit.problems:
                yield Violation(
                    "FIX-003",
                    Severity.ERROR if is_error else Severity.WARN,
                    message,
                    "BS 6465-2 / عرف الإسكان البريطاني",
                    s.index, (rid,),
                    f"منضدة {audit.usable_run_mm} مم، "
                    f"مجاز {audit.gangway_mm} مم "
                    f"(أضلاع {'+'.join(audit.sides) or '—'})",
                    f"≥ {audit.required_run_mm} مم / "
                    f"≥ {audit.required_gangway_mm} مم",
                )


def f_drainage_runs(
    dwg: Drawing, brief: Brief, out: FixtureOutcome
) -> Iterable[Violation]:
    """
    المسافة من كل تجهيز محتاج صرفًا إلى أقرب نظير في الدور الأسفل.

    تحذير لا خطأ: المسافة الطويلة تعني مجرى أفقيًا مكلفًا وقد تفرض سقفًا
    مُنزَلًا، لكنها ليست مخالفة. `GEO-011` يقيس نفس الفكرة على مستوى
    الغرف، وهذه على مستوى التجهيز — أدقّ وأقرب إلى التنفيذ.
    """
    ordered = sorted(dwg.storeys, key=lambda s: s.index)
    for lower, upper in zip(ordered, ordered[1:]):
        lower_pts = [
            f.centroid for f in lower.fixtures
            if FIX.needs_drain(f.code)
        ]
        if not lower_pts:
            continue
        for f in upper.fixtures:
            if not FIX.needs_drain(f.code):
                continue
            cx, cy = f.centroid
            d = min(abs(px - cx) + abs(py - cy) for px, py in lower_pts)
            if d > DRAIN_RUN_WARN_MM:
                yield Violation(
                    "FIX-004", Severity.WARN,
                    f"التجهيز {f.id} ({f.code}) بعيد عن أقرب عمود صرف أسفله",
                    "كفاءة تنفيذية", upper.index, (f.room,),
                    fmt_m(d), f"≤ {fmt_m(DRAIN_RUN_WARN_MM)}",
                )


def f_activity_inside_room(
    dwg: Drawing, brief: Brief, out: FixtureOutcome
) -> Iterable[Violation]:
    """
    شبكة أمان: حيّز استخدام خارج غرفته يعني خطأً في الحزم لا في التصميم.

    سقوطها يستوجب فحص `pack.py`، لا تعديل المتطلب.
    """
    for s in dwg.storeys:
        by_id = {r.id: r for r in s.rooms}
        for f in s.fixtures:
            room = by_id.get(f.room)
            if room is None:
                continue
            ax, ay, aw, ah = f.activity
            if (ax < room.x or ay < room.y
                    or ax + aw > room.x2 or ay + ah > room.y2):
                yield Violation(
                    "FIX-005", Severity.ERROR,
                    f"حيّز استخدام {f.id} ({f.code}) يخرج من الغرفة",
                    "سلامة هندسية", s.index, (f.room,),
                    f"({ax},{ay})–({ax + aw},{ay + ah})",
                    f"({room.x},{room.y})–({room.x2},{room.y2})",
                )


FIXTURE_CHECKS: list[Rule] = [
    Rule("FIX-FURN", "قابلية التأثيث",
         "ADM (رسومات الخلوص) / BS 6465-2", f_unfurnishable,
         frozenset({"fixtures"}), ("FIX-001",)),
    Rule("FIX-TURN", "خلوص الدوران",
         "ADM Vol 1", f_turning_space,
         frozenset({"fixtures", "access"}), ("FIX-002",)),
    Rule("FIX-KTCH", "تدقيق المطبخ",
         "BS 6465-2 / عرف الإسكان", f_kitchen,
         frozenset({"fixtures"}), ("FIX-003",)),
    Rule("FIX-DRAIN", "أعمدة الصرف",
         "كفاءة تنفيذية", f_drainage_runs,
         frozenset({"fixtures", "vertical"}), ("FIX-004",)),
    Rule("FIX-ACTV", "حيّزات الاستخدام",
         "سلامة هندسية", f_activity_inside_room,
         frozenset({"fixtures"}), ("FIX-005",)),
]

FIXTURE_CODES: frozenset[str] = frozenset(
    c for r in FIXTURE_CHECKS for c in r.emits
)


def check_fixtures(
    dwg: Drawing,
    brief: Brief,
    out: FixtureOutcome,
    tags: set[str] | None = None,
) -> ComplianceReport:
    rep = ComplianceReport(project_name=dwg.project_name)
    for rule in FIXTURE_CHECKS:
        if tags and not (rule.tags & tags):
            continue
        rep.rules_run.extend(rule.emits)
        rep.violations.extend(rule.check(dwg, brief, out))
    rep.sort()
    return rep
