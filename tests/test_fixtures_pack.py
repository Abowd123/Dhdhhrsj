"""
انحدارات الحزم.

`test_basin_parity_regression` يحرس العيب الذي كان يُبطل الأنبوب كله:
تمركز حيّز الاستخدام على عرض التجهيز يفرض تكافؤًا حسابيًا، فالمغسلة
(550 مم جسم، 700 مم حيّز، شبكة 50 مم) تجعل القيد متعذّرًا لأي موضع —
فيفشل كل حمام ودورة مياه ومطبخ، ولا يجوز أي مخطط أبدًا.
"""
from __future__ import annotations
import pytest
from planforge.codes.uk.fixtures_profile import FIX
from planforge.enums import AccessStandard
from planforge.fixtures.pack import GRID, minimal_envelope, pack_room
from planforge.units import m2


def test_basin_parity_regression():
    """المغسلة وحدها في غرفة معقولة يجب أن تُحزم."""
    res = pack_room(
        room_rect=(0, 0, 2000, 2000),
        codes=("BASIN",),
        door_zones=[(0, 0, 800, 800)],
        access=AccessStandard.M4_1,
    )
    assert res.ok, res.reason


def test_wc_set_has_a_minimum():
    env = minimal_envelope(("WC", "BASIN"), AccessStandard.M4_1, 0, 800)
    assert env.ok, "أصغر دورة مياه لا تُحلّ — عيب الزوجية عاد"
    assert env.min_dim >= 700
    assert env.area <= m2(4.0), (
        f"أصغر دورة مياه {env.min_dim}×{env.max_dim} مم — كبيرة بلا سبب"
    )


@pytest.mark.parametrize(
    "codes",
    [
        ("WC", "BASIN"),
        ("SHOWER", "WC", "BASIN"),
        ("BATH", "WC", "BASIN"),
        ("WM", "SINK"),
        ("BED_S", "WARDROBE"),
        ("BED_D", "WARDROBE"),
        ("SINK", "HOB", "FRIDGE"),
    ],
)
def test_every_required_set_is_packable(codes):
    """
    كل طقم مطلوب يجب أن يكون له حد أدنى.

    طقمٌ بلا حل يعني أن كل غرفة من نوعه تُصدر FIX-001 مهما كان حجمها —
    وهذا يُبطل نوع الغرفة كله لا حكمًا واحدًا.
    """
    env = minimal_envelope(codes, AccessStandard.M4_1, 0, 900)
    assert env.ok, f"{codes} لا يُحزم في أي غرفة"


def test_all_catalogue_sets_covered():
    """كل نوع غرفة له طقم، وكل رمز في الطقم موجود في الكتالوج."""
    for rtype, codes in FIX.required.items():
        for code in codes:
            assert code in FIX.catalogue, f"{rtype}: رمز مجهول {code}"


def test_activity_never_narrower_than_body():
    """
    الاحتواء يقتضي أن الحيّز أعرض من الواجهة أو يساويها.

    لو ضاق لصار قيد `_cover_x` متعذّرًا — وهو ما يحرسه هذا الاختبار على
    مستوى البيانات لا الحزم.
    """
    for code, spec in FIX.catalogue.items():
        assert spec.activity_w >= spec.w or not spec.against_wall, code
        assert spec.activity_d > 0, code


def test_grid_rounding_is_conservative():
    """
    الغرفة تُقلَّص إلى الشبكة، فلا يُجاز ما لا يُنفَّذ.

    غرفة أضيق من الحد بفارق دون خطوة الشبكة يجب أن تُرفض، لا أن تُوسَّع
    إلى ما يجوز.
    """
    tight = pack_room(
        room_rect=(0, 0, GRID - 10, 4000),
        codes=("WC",),
        door_zones=[],
        access=AccessStandard.M4_1,
    )
    assert not tight.ok
    assert "الشبكة" in tight.reason


def test_turning_space_enlarges_minimum():
    small = minimal_envelope(("WC", "BASIN"), AccessStandard.M4_1, 0, 900)
    big = minimal_envelope(("WC", "BASIN"), AccessStandard.M4_3, 1500, 900)
    assert big.ok and small.ok
    assert big.area > small.area, (
        "خلوص الدوران لم يكبّر الحد الأدنى — القيد غير مفروض"
    )


def test_failure_reports_a_minimum():
    """
    الفشل يحمل أصغر غرفة ممكنة.

    الرسالة «لا يمكن الحزم» بلا رقم غير قابلة للتصرّف: المهندس يحتاج
    الهدف لا الرفض.
    """
    res = pack_room(
        room_rect=(0, 0, 900, 900),
        codes=("BATH", "WC", "BASIN"),
        door_zones=[(0, 0, 800, 800)],
        access=AccessStandard.M4_1,
    )
    assert not res.ok
    assert res.minimum is not None and res.minimum.ok
    assert "أصغر غرفة" in res.reason
