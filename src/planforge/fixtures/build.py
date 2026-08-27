"""تجهيز كل غرف الرسم: حزم، تدقيق مطبخ، واستنباط الأبعاد الدنيا."""
from __future__ import annotations
from planforge.codes.uk.fixtures_profile import FIX
from planforge.codes.uk.profile import UK
from planforge.drawing.model import (
    ClearRoom, Drawing, PlacedFixture, PlacedOpening, StoreyDrawing,
)
from planforge.enums import Axis, CIRCULATION, RoomType, WET
from planforge.fixtures.kitchen import audit_kitchen
from planforge.fixtures.pack import minimal_envelope, pack_room
from planforge.fixtures.result import FixtureOutcome, MinEnvelope
from planforge.model.brief import Brief

KITCHEN_TYPES = frozenset({RoomType.KITCHEN, RoomType.KITCHEN_DINING})


def _door_zone(
    o: PlacedOpening, room: ClearRoom
) -> tuple[int, int, int, int]:
    """
    مربع دوران الباب داخل الغرفة التي يفتح إليها.

    الجهة تُقرأ من `swing_positive` المحسوب في `place_openings`، لا
    بتخمين من موقع الفتحة: باب على جدار داخلي بين غرفتين قد يفتح إلى
    أيّهما، والفرق مربعُ دوران في المكان الخطأ.
    """
    s = o.clear_width_mm
    if o.axis is Axis.V:
        x = o.coord if o.swing_positive else o.coord - s
        return (x, o.start, s, s)
    y = o.coord if o.swing_positive else o.coord - s
    return (o.start, y, s, s)


def _stack_point(
    st: StoreyDrawing, room: ClearRoom
) -> tuple[int, int] | None:
    """
    نقطة مرجعية لعمود المواسير: الحدّ الأقرب إلى أقرب غرفة رطبة مجاورة.

    ليست موضع العمود الحقيقي — النظام لا يُنمذج المواسير. غرضها توجيه
    التجهيزات المحتاجة صرفًا إلى جهة واحدة بدل تفرّقها على أربعة جدران،
    فيقصر مسار الصرف. غياب جار رطب يُعيد مركز الغرفة.
    """
    others = [
        r for r in st.rooms if r.id != room.id and r.type in WET
    ]
    if not others:
        return room.centroid
    cx, cy = room.centroid
    best = min(
        others,
        key=lambda r: (
            abs(r.centroid[0] - cx) + abs(r.centroid[1] - cy), r.id
        ),
    )
    bx, by = best.centroid
    return (
        min(max(bx, room.x), room.x2),
        min(max(by, room.y), room.y2),
    )


def furnish(
    drawing: Drawing, brief: Brief, *, deterministic: bool = False
) -> FixtureOutcome:
    """
    يُطبَّق على الرسم مباشرة: يملأ `fixtures` و`fixture_failures`.

    التعديل في المكان مقصود: التجهيزات سمة من الرسم لا كائن مستقل،
    ونسخُ الرسم لكل بديل يضاعف الذاكرة بلا مقابل.
    """
    out = FixtureOutcome()

    for st in drawing.storeys:
        st.fixtures = []
        st.fixture_failures = []
        n = 0
        for room in st.rooms:
            if room.type in CIRCULATION:
                continue
            codes = FIX.set_for(room.type)
            if not codes:
                continue

            zones = [
                _door_zone(o, room)
                for o in st.openings
                if o.is_door and o.swing_to == room.id
            ]
            turning = FIX.turning_for(room.type, brief.access_standard)

            res = pack_room(
                room_rect=(room.x, room.y, room.w, room.h),
                codes=codes,
                door_zones=zones,
                access=brief.access_standard,
                turning_mm=turning,
                stack_point=_stack_point(st, room),
                deterministic=deterministic,
            )
            if not res.ok:
                msg = f"[دور {st.index}] {room.id} ({room.type}): {res.reason}"
                out.failures.append(msg)
                st.fixture_failures.append(msg)
                out.unfurnishable[room.id] = res.minimum or minimal_envelope(
                    codes, brief.access_standard, turning,
                    max((z[2] for z in zones), default=900),
                    deterministic,
                )
                continue

            for p in res.placements:
                n += 1
                st.fixtures.append(PlacedFixture(
                    id=f"F{st.index}{n:02d}", code=p.code, room=room.id,
                    x=p.x, y=p.y, w=p.w, h=p.h,
                    rotation_deg=p.rotation_deg, activity=p.activity,
                ))

            if room.type in KITCHEN_TYPES:
                out.kitchens[room.id] = audit_kitchen(
                    room,
                    st.openings_of(room.id),
                    st.fixtures_of(room.id),
                    bedspaces=brief.bedspaces,
                    access=brief.access_standard,
                )
    return out


def derive_min_dimensions(
    brief: Brief, *, deterministic: bool = False
) -> dict[str, MinEnvelope]:
    """
    لكل غرفة في المتطلب: أصغر مظروف يستوعب طقمها.

    تُستخدم قبل التوليد لتضييق فضاء الحل على ما يقبل التأثيث فعلًا —
    أول حلقات التغذية الراجعة الثلاث. الباب مفترض بخلوص ADM للفئة
    المطلوبة، فرفع معيار الوصول يرفع الأبعاد الدنيا تلقائيًا.
    """
    door = UK.door_min_clear_width[brief.access_standard]
    out: dict[str, MinEnvelope] = {}
    for r in brief.rooms:
        codes = FIX.set_for(r.type)
        if not codes:
            continue
        turning = FIX.turning_for(r.type, brief.access_standard)
        env = minimal_envelope(
            codes, brief.access_standard, turning, door, deterministic
        )
        if env.ok:
            out[r.id] = env
    return out
