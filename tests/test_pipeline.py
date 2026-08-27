"""
الأنبوب الكامل: من متطلب إلى مخطط مُدقَّق أربع مرات.

هذا الاختبار البطيء الوحيد المقبول: يقيس أن الحلقتين تتقاربان فعلًا،
وهو ما لا يقيسه شيء آخر.
"""
from __future__ import annotations
import pytest
from planforge.rules.brief_rules import check_brief


def test_brief_is_feasible(brief, fast_cfg):
    rep = check_brief(brief, fast_cfg)
    assert rep.ok, [
        f"{v.rule_id}: {v.message}" for v in rep.errors
    ]


def test_pipeline_produces_a_drawing(solved):
    assert solved.drawing.storeys
    st = solved.drawing.storeys[0]
    assert st.runs, "لا جدران"
    assert st.rooms, "لا غرف"
    assert st.openings, "لا فتحات"


def test_clear_areas_are_smaller_than_centreline(solved):
    """
    كل غرفة صافية أصغر من مساحتها على خط المركز.

    لو تساوت لَما جرى خصم الجدران، وكل حكم في طبقة الرسم يقيس رقمًا
    مبالغًا فيُجيز ما لا يُنفَّذ.
    """
    for st in solved.drawing.storeys:
        for r in st.rooms:
            assert r.area < r.centerline_area_mm2, r.id
            assert 0.75 < r.shrink_ratio < 1.0, (
                f"{r.id}: انكماش {r.shrink_ratio:.3f} خارج المعقول"
            )


def test_shrink_is_measured_not_compensated(solved):
    """
    الانكماش يُقاس ويُبلَّغ. الحلقة التي كانت تضخّم المستهدفات أُسقطت:
    مجموع المساحات مقيَّد بالمظروف، فالتضخيم الموحّد لا يغيّر التوزيع.
    """
    assert 0.75 < solved.shrink_ratio < 1.0
    assert solved.rounds >= 1
    for note in solved.shrink_notes:
        assert "ارفع المستهدف" in note, "ملاحظة غير قابلة للتصرّف"


def test_every_room_reachable_by_a_door(solved):
    from planforge.enums import CIRCULATION

    for st in solved.drawing.storeys:
        served = {
            rid for o in st.openings if o.is_door for rid in o.rooms()
        }
        for r in st.rooms:
            if r.type in CIRCULATION:
                continue
            assert r.id in served, f"{r.id} بلا باب"


def test_openings_lie_within_their_walls(solved):
    for st in solved.drawing.storeys:
        for o in st.openings:
            assert st.run_carrying(o) is not None, (
                f"{o.id} لا يقع داخل مسار جدار واحد"
            )


def test_reports_ran_something(solved):
    for rep in (
        solved.layout_report, solved.drawing_report, solved.fixture_report
    ):
        assert rep.rules_run, "تقرير بلا قاعدة مُشغَّلة"


def test_features_are_sane(solved):
    f = solved.features
    assert 0.0 <= f.circulation_ratio < 0.6
    assert f.clear_gia_m2 > 0
    assert 0.0 <= f.wet_stack_ratio <= 1.0
    assert 0.0 <= f.structural_alignment_ratio <= 1.0


def test_assurance_blocks_delivery_by_default(solved):
    """
    بلا توقيعات، الختم NOT FOR CONSTRUCTION.

    هذا الثبات الجوهري في المشروع: مخرجٌ لم تُصدَّق أرقامه لا يُسلَّم،
    ولا يُرفع الختم بعَلَم في سطر أوامر.
    """
    from planforge.assurance import assess
    from planforge.codes.signing import SignatureBook

    a = assess(
        [
            solved.layout_report, solved.drawing_report,
            solved.fixture_report,
        ],
        book=SignatureBook(),
    )
    assert a.relied_on, "لا رقم استند إليه أي حكم — الخريطة مكسورة"
    assert not a.delivery_ready
    assert "NOT FOR CONSTRUCTION" in a.stamp()
