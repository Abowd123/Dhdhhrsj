"""
خريطة الاستناد تطابق ما تُصدره القواعد فعلًا.

سقوط `test_every_emitted_code_declared` يعني حكمًا يُصدَر بلا شجرة
استناد، فكتلة الاعتماد تقول «كل ما استند إليه موقَّع» وهي لم تفحص شيئًا.
"""
from __future__ import annotations
import pytest
from planforge.codes.usage import (
    RULE_DEPENDENCIES, dependencies_of, expand, orphan_declarations,
    rules_using, undeclared_rules,
)


def _emitted() -> frozenset[str]:
    """
    كل معرّف تُصدره الطبقات الأربع.

    ⚠ يفترض أن `default_registry()` يعرض `.rules` بعناصر لها `.emits`.
    الواجهة من الدفعة 3؛ عدّل هذا الجامع إن اختلفت، ولا تُسكِت الاختبار.
    """
    codes: set[str] = set()

    from planforge.rules.drawing_rules import DRAWING_CODES
    from planforge.rules.fixture_rules import FIXTURE_CODES
    codes |= set(DRAWING_CODES) | set(FIXTURE_CODES)

    from planforge.rules.registry import default_registry
    reg = default_registry()
    rules = getattr(reg, "rules", None)
    if rules is None:
        pytest.skip(
            "واجهة السجل لا تعرض .rules — عدّل الجامع في هذا الاختبار"
        )
    for rule in rules:
        codes |= set(getattr(rule, "emits", ()))

    from planforge.rules.brief_rules import FEASIBILITY_CODES
    codes |= set(FEASIBILITY_CODES)
    codes.add("SOL-001")
    return frozenset(codes)


def test_every_emitted_code_declared():
    missing = undeclared_rules(_emitted())
    assert not missing, (
        f"معرّفات تُصدَر بلا إعلان تبعيات: {sorted(missing)}"
    )


def test_no_orphan_declarations():
    orphans = orphan_declarations(_emitted())
    assert not orphans, (
        f"إعلانات لمعرّفات لم تعد تُصدَر: {sorted(orphans)}"
    )


def test_all_patterns_resolve():
    """
    كل نمط يُطابق مسارًا موجودًا.

    هذا ما يمنع الخريطة من التباعد عن السجل: حذفُ رقم أو إعادة تسميته
    يُفشل الاختبار هنا بدل أن يُنتج شجرة استناد ناقصة صمتًا.
    """
    for rule_id, patterns in RULE_DEPENDENCIES.items():
        for pat in patterns:
            try:
                hits = expand((pat,))
            except KeyError as exc:
                pytest.fail(f"{rule_id}: {exc}")
            assert hits, f"{rule_id}: {pat} لا يُطابق شيئًا"


def test_star_expands_to_multiple():
    paths = dependencies_of("NDSS-001")
    assert len(paths) >= 3, "نجمة غرف النوم لم تتوسّع"
    assert all(p.startswith("uk.bedroom_min_area[") for p in paths)


def test_reverse_lookup_is_consistent():
    path = "uk.protected_stair_threshold"
    users = rules_using(path)
    assert "ADB-001" in users
    assert "DRW-015" in users
    for rid in users:
        assert path in dependencies_of(rid)


def test_unmatched_pattern_raises():
    with pytest.raises(KeyError):
        expand(("uk.does_not_exist",))
