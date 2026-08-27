"""
الحالات المرجعية: مخططات معلومة الحكم مسبقًا.

هذه الطريقة الوحيدة لتصحيح رقم بأمان: تغيّر الرقم، تشغّل الحالات، ترى
أي حكم انقلب. بلا ذلك يكون كل تصحيح قفزة في الظلام.

⚠ الحالات المرفقة **تركيبية**، لا مخططات معتمدة حقيقية. قيمتها في كشف
الانقلابات لا في تصديق الأرقام: تحمي من الانحدار ولا تصدّق رقمًا.
استبدلها بمخططات مرّت على سلطة رقابية فعلًا — يومَها تصير مجموعة تصديق.
"""
from __future__ import annotations
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from planforge.drawing.build import build_drawing
from planforge.fixtures.result import FixtureOutcome
from planforge.model.brief import Brief
from planforge.model.layout import Layout
from planforge.rules.core import ComplianceReport, Severity
from planforge.rules.drawing_rules import check_drawing
from planforge.rules.fixture_rules import check_fixtures
from planforge.rules.registry import default_registry

SOURCE_SYNTHETIC = "synthetic"
SOURCE_APPROVED = "approved"
SOURCE_REJECTED = "rejected"
VALID_SOURCES = frozenset({
    SOURCE_SYNTHETIC, SOURCE_APPROVED, SOURCE_REJECTED
})


@dataclass
class GoldenCase:
    name: str
    source: str
    provenance: str
    brief: Brief
    layout: Layout
    expect_errors: set[str] = field(default_factory=set)
    expect_clean: bool = False
    note: str = ""

    @classmethod
    def load(cls, path: Path) -> GoldenCase:
        raw = json.loads(path.read_text(encoding="utf-8"))
        source = raw.get("source", SOURCE_SYNTHETIC)
        if source not in VALID_SOURCES:
            raise ValueError(
                f"{path.name}: مصدر غير معروف {source!r} — "
                f"المسموح {sorted(VALID_SOURCES)}"
            )
        return cls(
            name=raw.get("name", path.stem),
            source=source,
            provenance=raw.get("provenance", ""),
            brief=Brief.model_validate(raw["brief"]),
            layout=Layout.model_validate(raw["layout"]),
            expect_errors=set(raw.get("expect_errors", ())),
            expect_clean=bool(raw.get("expect_clean", False)),
            note=raw.get("note", ""),
        )


@dataclass(frozen=True, slots=True)
class CaseResult:
    name: str
    source: str
    actual_errors: frozenset[str]
    missing: frozenset[str]      # توقّعناها ولم تظهر
    unexpected: frozenset[str]   # ظهرت ولم نتوقّعها

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unexpected


def evaluate(case: GoldenCase, *, skip_fixtures: bool = False) -> set[str]:
    dwg, problems = build_drawing(case.layout, case.brief)
    reports = [
        default_registry().run(case.layout, case.brief),
        check_drawing(dwg, case.brief, problems),
    ]
    if not skip_fixtures:
        from planforge.fixtures.build import furnish
        out = furnish(dwg, case.brief, deterministic=True)
        reports.append(check_fixtures(dwg, case.brief, out))
    else:
        reports.append(
            check_fixtures(dwg, case.brief, FixtureOutcome.empty())
        )
    return {
        v.rule_id
        for rep in reports for v in rep.violations
        if v.severity is Severity.ERROR
    }


def run_all(
    golden_dir: Path, *, skip_fixtures: bool = False
) -> list[CaseResult]:
    out: list[CaseResult] = []
    for path in sorted(golden_dir.glob("*.json")):
        case = GoldenCase.load(path)
        actual = evaluate(case, skip_fixtures=skip_fixtures)
        expected = set() if case.expect_clean else case.expect_errors
        out.append(CaseResult(
            name=case.name, source=case.source,
            actual_errors=frozenset(actual),
            missing=frozenset(expected - actual),
            unexpected=frozenset(actual - expected),
        ))
    return out


# ═══════════════ قياس أثر تغيير رقم ═══════════════

_ACTIVE: set[str] = set()


def _resolve(path: str) -> tuple[Any, Any]:
    """
    يُعيد (الحاوية، المفتاح) للمسار.

    الحاوية إما القاموس (للمسارات المُفهرَسة) أو كائن الملف نفسه.
    """
    from planforge.codes.uk.detail_profile import DETAIL
    from planforge.codes.uk.fixtures_profile import FIX
    from planforge.codes.uk.profile import UK

    roots = {"uk": UK, "fix": FIX, "detail": DETAIL}
    head, _, rest = path.partition(".")
    root = roots.get(head)
    if root is None or not rest:
        raise KeyError(f"مسار غير معروف: {path}")

    if "[" not in rest:
        if not hasattr(root, rest):
            raise KeyError(f"حقل غير موجود: {path}")
        return root, rest

    field_name, _, tail = rest.partition("[")
    key = tail.rstrip("]").split("].")[0]
    container = getattr(root, field_name, None)
    if not isinstance(container, dict):
        raise KeyError(f"مسار مُفهرَس على غير قاموس: {path}")
    for k in container:
        if (k.value if hasattr(k, "value") else str(k)) == key:
            return container, k
    raise KeyError(f"مفتاح غير موجود: {path}")


def _invalidate_caches() -> None:
    """
    `minimal_envelope` مُخزَّنة بـlru_cache، فتعديل رقم يدخل في حسابها لا
    يظهر أثره بلا إبطالها — و`codes impact` كان يُبلّغ «لا انقلاب» وهو لم
    يُعِد الحساب أصلًا. صمتٌ يُقرأ ضمانًا.
    """
    from planforge.fixtures.pack import minimal_envelope
    minimal_envelope.cache_clear()


@contextmanager
def override(path: str, value: Any) -> Iterator[None]:
    """
    يكتب قيمة في ملف كود مؤقتًا، ويُرجعها في `finally`.

    ملفات الكود `frozen dataclass`، فالكتابة تمرّ بـ`object.__setattr__`.
    هذا مقبول في أداة قياس أثر تضمن الإرجاع، وغير مقبول في أي مسار
    إنتاج — ولذلك حُصر في مدير سياق يرفض التداخل: تعديلان متزامنان على
    المسار نفسه يجعلان الإرجاع غير محدَّد.
    """
    if path in _ACTIVE:
        raise RuntimeError(f"تعديل متداخل على المسار نفسه: {path}")
    container, key = _resolve(path)
    is_dict = isinstance(container, dict)
    old = container[key] if is_dict else getattr(container, key)

    _ACTIVE.add(path)
    try:
        if is_dict:
            container[key] = value
        else:
            object.__setattr__(container, key, value)
        _invalidate_caches()
        yield
    finally:
        if is_dict:
            container[key] = old
        else:
            object.__setattr__(container, key, old)
        _invalidate_caches()
        _ACTIVE.discard(path)


def compare_with_override(
    golden_dir: Path,
    path: str,
    value: Any,
    *,
    skip_fixtures: bool = True,
) -> list[dict[str, str]]:
    """يُعيد الأحكام التي تنقلب لو صار `path` يساوي `value`."""
    cases = [
        GoldenCase.load(p) for p in sorted(golden_dir.glob("*.json"))
    ]
    if not cases:
        return []
    before = {
        c.name: evaluate(c, skip_fixtures=skip_fixtures) for c in cases
    }
    with override(path, value):
        after = {
            c.name: evaluate(c, skip_fixtures=skip_fixtures) for c in cases
        }

    flips: list[dict[str, str]] = []
    for name in sorted(before):
        for rule in sorted(before[name] | after[name]):
            was, now = rule in before[name], rule in after[name]
            if was != now:
                flips.append({
                    "case": name,
                    "rule": rule,
                    "before": "مخالفة" if was else "مطابق",
                    "after": "مخالفة" if now else "مطابق",
                })
    return flips
