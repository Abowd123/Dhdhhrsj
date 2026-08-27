"""
حل الفتحات هندسيًا على شبكة الجدران.

لا نثق بمواضع طبقة الصقل؛ نُعيد الحل على الجدران الحقيقية مع كتفٍ عند
كل طرف. عرض الفتحة الإنشائي = الخلوص + إطار على كل جانب، وهذا ما يُقطع
من الجدار فعلًا — وهو الفرق بين مخطط يُنفَّذ ومخطط يبدو صحيحًا.

تلميحات المواضع (`hints`) تُمرَّر معاملًا لا حالةً عالمية: المحرر يحفظ
موضعًا ضبطه المهندس، والنسخة التي كانت تخزّنه في متغير وحدة تُسرّبه بين
الجلسات في العملية نفسها.
"""
from __future__ import annotations
from planforge.codes.uk.detail_profile import DETAIL
from planforge.codes.uk.profile import UK
from planforge.drawing.model import PlacedOpening, WallFace
from planforge.enums import AccessStandard, Axis, CIRCULATION, OpeningKind
from planforge.geometry.rect import Rect
from planforge.geometry.stair import solve_straight_flight
from planforge.model.brief import Brief
from planforge.model.layout import StoreyLayout

FRAME_MM = DETAIL.door_frame_mm            # يبقى الاسم: drawing_rules يستورده
JAMB_NIB_MM = DETAIL.jamb_nib_min_mm
WINDOW_CORNER_MM = DETAIL.window_corner_offset_mm
WINDOW_HEAD_MM = DETAIL.window_head_mm
OPENABLE_FRACTION = DETAIL.window_openable_fraction
DOOR_HEAD_MM = 2040
MIN_WINDOW_MM = 600
STAIR_STEPS_MAX = 24


def _side_nib(brief: Brief) -> int:
    """ADM: كتف 300 مم بجانب الباب عند الاقتراب الجانبي (M4(2)/(3))."""
    if brief.access_standard is AccessStandard.M4_1:
        return JAMB_NIB_MM
    return max(JAMB_NIB_MM, UK.door_side_nib)


def _pick_face(
    faces: list[WallFace], rooms: frozenset[str], need: int
) -> WallFace | None:
    """أطول جدار مشترك بين الغرفتين. المطابق للحاجة أولًا، وإلا الأطول."""
    same = [f for f in faces if f.rooms() == rooms]
    if not same:
        return None
    usable = [f for f in same if f.length >= need]
    pool = usable or same
    return max(pool, key=lambda f: (f.length, f.coord, f.lo))


def _external_faces(faces: list[WallFace], rid: str) -> list[WallFace]:
    return [
        f for f in faces
        if (f.a is None and f.b == rid) or (f.b is None and f.a == rid)
    ]


def _positioned(
    face: WallFace, width: int, margin: int, hint: float | None
) -> int:
    """موضع بداية الفتحة على الجدار، محصورًا داخل الكتفين."""
    span = face.length - 2 * margin - width
    if hint is None:
        start = face.lo + margin + max(0, span) // 2
    else:
        start = face.lo + margin + int(max(0, span) * hint)
    lo = face.lo + margin
    hi = face.hi - margin - width
    return max(lo, min(start, max(lo, hi)))


def _swing_sign(
    face: WallFace, target: Rect | None
) -> bool:
    """
    هل يفتح الباب نحو الاتجاه الموجب للمحور العمودي على الجدار؟

    يُقاس من موقع مركز الغرفة التي يفتح إليها. غيابُ الغرفة (باب خارجي)
    يُعيد True: الباب الخارجي يفتح إلى الداخل، وهو الاتجاه الموجب من
    منظور الجدار الجنوبي/الغربي في اصطلاحنا.
    """
    if target is None:
        return True
    cx, cy = target.centroid
    return (cx > face.coord) if face.axis is Axis.V else (cy > face.coord)


def place_openings(
    storey: StoreyLayout,
    faces: list[WallFace],
    clear: dict[str, Rect],
    brief: Brief,
    *,
    hints: dict[str, float] | None = None,
) -> tuple[list[PlacedOpening], list[str]]:
    """
    يُعيد (الفتحات المحلولة، رسائل الفشل).

    الفشل ليس استثناءً — هو معلومة تُرفع للمُدقِّق كخطأ `DRW-000`. فتحةٌ
    لا تُحلّ هندسيًا أخطر من فتحة خاطئة: الأولى تُنتج مخططًا بغرفة بلا
    باب، والثانية تُلتقط بقاعدة.
    """
    hints = hints or {}
    nib = _side_nib(brief)
    types = {r.id: r.type for r in storey.rooms}
    door_min = UK.door_min_clear_width[brief.access_standard]
    problems: list[str] = []
    out: list[PlacedOpening] = []

    for op in storey.openings:
        clear_w = op.clear_width_mm
        hint = hints.get(op.id)

        # ── فتحة داخلية ──
        if op.b is not None:
            need = clear_w + 2 * FRAME_MM + 2 * nib
            face = _pick_face(faces, frozenset({op.a, op.b}), need)
            if face is None:
                problems.append(
                    f"{op.id}: لا جدار مشترك بين {op.a} و {op.b}"
                )
                continue
            if face.length < need:
                problems.append(
                    f"{op.id}: الجدار بين {op.a} و {op.b} طوله "
                    f"{face.length} مم ولا يستوعب فتحة {clear_w} مم مع كتف "
                    f"{nib} مم (المطلوب {need} مم)"
                )
                continue

            start = _positioned(face, clear_w, FRAME_MM + nib, hint)

            # الباب يفتح إلى الحركة إن أمكن، وإلا إلى الغرفة الأوسع:
            # فتح الباب على ممر يوفّر مساحة الغرفة ويُبعد القوس عن الأثاث.
            circ = [r for r in (op.a, op.b) if types.get(r) in CIRCULATION]
            if len(circ) == 1:
                swing = circ[0]
            else:
                swing = max(
                    (op.a, op.b),
                    key=lambda r: (clear[r].area if r in clear else 0, r),
                )

            out.append(PlacedOpening(
                id=op.id, kind=op.kind, axis=face.axis, coord=face.coord,
                start=start, clear_width_mm=clear_w,
                thickness_mm=face.thickness_mm,
                head_mm=DOOR_HEAD_MM, sill_mm=0,
                room_a=op.a, room_b=op.b, swing_to=swing,
                swing_positive=_swing_sign(face, clear.get(swing)),
                hinge_left=(start - face.lo) <= (face.hi - start - clear_w),
                fire_rating=(
                    f"FD{UK.fire_rating_minutes_int}"
                    if op.kind is OpeningKind.FIRE_DOOR else ""
                ),
            ))
            continue

        # ── فتحة خارجية ──
        ext = _external_faces(faces, op.a)
        if not ext:
            problems.append(f"{op.id}: الغرفة {op.a} بلا واجهة خارجية")
            continue

        is_window = op.kind in {
            OpeningKind.WINDOW, OpeningKind.ESCAPE_WINDOW
        }
        margin = WINDOW_CORNER_MM if is_window else nib
        usable = [f for f in ext if f.length >= clear_w + 2 * margin]
        face = max(
            usable or ext, key=lambda f: (f.length, f.coord, f.lo)
        )
        avail = face.length - 2 * margin
        if avail < MIN_WINDOW_MM:
            problems.append(
                f"{op.id}: واجهة {op.a} طولها {face.length} مم — "
                f"لا تستوعب فتحة (المتاح بعد الزوايا {max(avail, 0)} مم)"
            )
            continue

        w = min(clear_w, avail)
        head = WINDOW_HEAD_MM if is_window else DOOR_HEAD_MM
        sill = op.sill_mm if is_window else 0
        openable = op.openable_area_mm2
        if is_window:
            # المساحة القابلة للتشغيل الفعلية: نصف الفتحة يُفتح في
            # النافذة المنزلقة/المحوَّرة القياسية. نأخذ الأصغر بين
            # المُعلن والممكن هندسيًا كي لا نُبلّغ عن تهوية غير متحققة.
            physical = int(w * max(0, head - sill) * OPENABLE_FRACTION)
            openable = min(openable, physical) if openable else physical
        elif not is_window and op.kind in {
            OpeningKind.DOOR, OpeningKind.FIRE_DOOR
        }:
            w = max(w, min(door_min, avail))

        out.append(PlacedOpening(
            id=op.id, kind=op.kind, axis=face.axis, coord=face.coord,
            start=_positioned(face, w, margin, hint), clear_width_mm=w,
            thickness_mm=face.thickness_mm, head_mm=head, sill_mm=sill,
            room_a=op.a, room_b=None, swing_to=op.a,
            swing_positive=_swing_sign(face, clear.get(op.a)),
            openable_area_mm2=openable,
        ))
    return out, problems


def stair_geometry(
    room_id: str, rect: Rect, floor_to_floor_mm: int
) -> tuple[tuple[int, ...], bool, int, float, int]:
    """
    مواضع القوائم واتجاه المجرى داخل بصمة السلّم.

    يُعيد (المواضع، أفقي؟، عدد القوائم، القائمة، النائمة). يُشتق من نفس
    دالة `solve_straight_flight` التي يفحصها `ADK-001`، فلا يظهر رسم
    يخالف الحكم.
    """
    sol = solve_straight_flight(
        floor_to_floor_mm, rect,
        max_rise_mm=UK.stair_max_rise,
        min_going_mm=UK.stair_min_going,
        max_pitch_deg=UK.stair_max_pitch_deg,
        twice_rise_plus_going=UK.stair_2r_plus_g,
        min_width_mm=UK.stair_min_width,
    )
    horizontal = rect.w > rect.h
    n = min(max(sol.n_risers, 0), STAIR_STEPS_MAX)
    if n < 2:
        return (), horizontal, sol.n_risers, sol.rise_mm, sol.going_mm

    span = rect.w if horizontal else rect.h
    base = rect.x if horizontal else rect.y
    step = span / n
    risers = tuple(int(base + step * i) for i in range(1, n))
    return risers, horizontal, sol.n_risers, sol.rise_mm, sol.going_mm
