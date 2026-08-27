"""
تغطية سجل الإثبات — أهم اختبار في المجموعة.

سقوطه يعني أن رقمًا يُقرأ في حكمٍ بلا مسار للتوقيع، أي أن بوابة التسليم
تُجيز ما لم يفحصه أحد. عيبٌ برمجي لا دَين مراجعة.
"""
from __future__ import annotations
import pytest
from planforge.codes.provenance import (
    REGISTRY, Confidence, SafetyDirection, coverage, enumerate_values,
    value_digest, values_of,
)
from planforge.codes.signing import SignatureBook, default_profiles


@pytest.fixture(scope="module")
def profiles():
    return default_profiles()


def test_no_coverage_gaps(profiles):
    gaps, total = coverage(profiles)
    assert total > 0, "لم يُعدّ أي رقم — تعداد القيم مكسور"
    assert not gaps, "فجوات: " + "; ".join(
        f"{g.path} ({g.reason})" for g in gaps[:10]
    )


def test_booleans_are_leaves(profiles):
    """
    `bool` فرعٌ من `int`، فترتيب الفحوص في `_walk` حسّاس.

    لو فُحص `_SKIP_TYPES` قبله لصار `hob_under_window_forbidden` سجلًّا
    بلا قيمة، فتُبلَّغ فجوة كاذبة ويسقط `codes audit`.
    """
    values = values_of(profiles)
    assert "fix.hob_under_window_forbidden" in values
    assert isinstance(values["fix.hob_under_window_forbidden"], bool)
    assert "uk.wc_at_entrance_storey_required" in values


def test_no_frozensets_enumerated(profiles):
    """التصنيفات لا تُوقَّع: مجموعةُ نطاقٍ ليست مقاسًا."""
    for path, value in values_of(profiles).items():
        assert not isinstance(value, (frozenset, set, str)), path


def test_statutory_numbers_have_clause():
    """كل رقم يحتاج توقيعًا يحمل مرجعًا، والقانوني يحمل فقرة."""
    for prov in REGISTRY.all():
        if not prov.needs_signature:
            continue
        assert prov.ref is not None, prov.path
        if prov.ref.is_statutory:
            assert prov.ref.clause.strip(), (
                f"{prov.path}: مرجع قانوني بلا فقرة"
            )


def test_high_risk_set_is_not_empty():
    """
    لو خلا السجل من `recalled` + `permissive` فالتصنيف لم يُطبَّق، لا أن
    الأرقام مُصدَّقة — واختبارٌ يمرّ لهذا السبب أسوأ من غيابه.
    """
    risky = REGISTRY.high_risk()
    assert risky, "لا رقم عالي الخطر — تحقّق أن التصنيف مُسنَد فعلًا"
    assert any(
        "protected_stair_threshold" in p.path for p in risky
    ), "منسوب السلّم المحمي يجب أن يكون في القائمة"


def test_signature_invalidated_by_value_change(profiles, tmp_path):
    from planforge.golden import override

    path = "uk.escape_window_min_dim"
    values = values_of(profiles)
    book = SignatureBook()
    book.sign(
        path, values[path], by="tester",
        clause="ADB Vol 1 2019 para 2.10",
    )
    assert book.status_of(path, values[path]).state == "signed"

    with override(path, 400):
        after = values_of(default_profiles())[path]
        assert after == 400
        assert book.status_of(path, after).state == "stale"

    assert book.status_of(path, values_of(default_profiles())[path]).state \
        == "signed", "مدير السياق لم يُرجع القيمة"


def test_sign_requires_clause_and_name(profiles):
    values = values_of(profiles)
    book = SignatureBook()
    with pytest.raises(ValueError):
        book.sign(
            "uk.escape_window_min_dim",
            values["uk.escape_window_min_dim"], by="", clause="x",
        )
    with pytest.raises(ValueError):
        book.sign(
            "uk.escape_window_min_dim",
            values["uk.escape_window_min_dim"], by="x", clause="  ",
        )


def test_engine_params_not_signable():
    book = SignatureBook()
    with pytest.raises(ValueError):
        book.sign("uk.edition", "x", by="t", clause="c")


def test_digest_is_stable_across_calls():
    a = value_digest((550, 700))
    b = value_digest((550, 700))
    assert a == b
    assert a != value_digest((550, 701))


def test_book_roundtrip(tmp_path, profiles):
    values = values_of(profiles)
    book = SignatureBook()
    book.sign(
        "uk.purge_vent_ratio", values["uk.purge_vent_ratio"],
        by="tester", clause="ADF Table 1.3",
    )
    path = book.save(tmp_path / "sigs.json")
    again = SignatureBook.load(path)
    assert len(again) == 1
    assert again.status_of(
        "uk.purge_vent_ratio", values["uk.purge_vent_ratio"]
    ).state == "signed"


def test_every_signable_path_is_read_by_some_rule():
    """
    رقمٌ يُوقَّع ولا يقرؤه حكم يُنتج توقيعًا كاذبًا: المراجع يُقرّ بصحّة ما
    لا أثر له، ويظنّ أنه أمّن حكمًا.

    الحالة المعروفة: `fix.worktop_beside_hob_min` و
    `fix.worktop_beside_sink_min` و `fix.catalogue[*].is_worktop` مسجَّلة
    ومُعلَنة، و`audit_kitchen` لا يقرؤها. القرار: تُنفَّذ أو تُحذف —
    و`test_no_orphan_declarations` لا يلتقطها لأنه يقارن معرّفات القواعد
    لا المسارات.
    """
    from planforge.codes.usage import rules_using

    orphans = [
        p.path for p in REGISTRY.all()
        if p.needs_signature and not rules_using(p.path)
    ]
    assert not orphans, f"أرقام تُوقَّع ولا يقرؤها حكم: {sorted(orphans)}"


def test_detail_profile_is_covered(profiles):
    """كل رقم في ملف التفاصيل معدود ومسجَّل — وهو مصدر أخطاء لا تحذيرات."""
    values = values_of(profiles)
    detail = {p for p in values if p.startswith("detail.")}
    assert len(detail) >= 20, f"عُدّ {len(detail)} رقمًا فقط في detail"
    assert "detail.window_openable_fraction" in detail
    assert "detail.pack_grid_mm" in detail
