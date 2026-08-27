"""
الحالات المرجعية: شبكة أمان لتغيير الأرقام.

هذا الاختبار لا يصدّق رقمًا — يكشف أن تغييره غيّر حكمًا. الفرق جوهري،
ومن يقرأ نجاحه تصديقًا يبني على وهم.
"""
from __future__ import annotations
from pathlib import Path
import pytest
from planforge.golden import compare_with_override, run_all

GOLDEN = Path(__file__).parent / "golden"


def test_golden_dir_has_cases():
    assert list(GOLDEN.glob("*.json")), "لا حالات مرجعية"


def test_cases_load_and_declare_provenance():
    from planforge.golden import GoldenCase

    for path in sorted(GOLDEN.glob("*.json")):
        case = GoldenCase.load(path)
        assert case.provenance.strip(), (
            f"{path.name}: حالة بلا بيان مصدر — "
            f"لا يُعرف أتصدّق أم تحرس"
        )


def test_cases_match_expectations():
    results = run_all(GOLDEN, skip_fixtures=True)
    bad = [r for r in results if not r.ok]
    assert not bad, "\n".join(
        f"{r.name}: ناقصة={sorted(r.missing)} "
        f"زائدة={sorted(r.unexpected)}"
        for r in bad
    )


def test_changing_a_number_flips_a_verdict():
    """
    مقياس صلاحية المجموعة نفسها.

    لو لم ينقلب شيء عند خفض حد مساحة غرفة النوم إلى الصفر، فالمجموعة لا
    تلمس هذا الرقم — فقياس أثر تصحيحه بلا معنى، وينبغي إضافة حالة.
    """
    flips = compare_with_override(
        GOLDEN, "uk.bedroom_min_area[bedroom_double]", 1,
        skip_fixtures=True,
    )
    if not flips:
        pytest.fail(
            "لا حكم ينقلب عند إبطال حد مساحة غرفة النوم — "
            "المجموعة لا تحرس هذا الرقم"
        )
    assert any(f["after"] == "مطابق" for f in flips)


def test_synthetic_cases_are_flagged():
    from planforge.golden import GoldenCase, SOURCE_SYNTHETIC

    cases = [GoldenCase.load(p) for p in sorted(GOLDEN.glob("*.json"))]
    synthetic = [c for c in cases if c.source == SOURCE_SYNTHETIC]
    assert len(synthetic) == len(cases), (
        "توجد حالات تُعلن نفسها معتمدة — "
        "تحقّق من مصدرها قبل الاعتماد عليها"
    )
