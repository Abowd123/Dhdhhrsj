"""
تدقيق المطبخ: طول المنضدة المتاح، عرض المجاز، وترتيب الحوض والطبّاخ.

المنضدة تُقاس على أطوال الجدران الصالحة لا على محيط الغرفة: الباب يقطع
المنضدة، والنافذة التي جلستها ≥ ارتفاع المنضدة **لا** تقطعها. الفرق ليس
تجميليًا — مطبخ 3.6 م بنافذتين عاليتين يعمل، ونفسه بنافذتين منخفضتين لا
يستوعب طقمه.

الحدّ المُعلن: هذا تدقيق تحليلي لا حلّ ترتيب. الحوض والطبّاخ يوضعان
بالحزم العام في `pack.py`، والمنضدة تُقاس على الجدران. مطبخ جزيرة أو
حرف U غير مُنمذَج، فطوله المتاح يُقاس أضلاعًا مستقيمة فقط.
"""
from __future__ import annotations
from planforge.codes.uk.detail_profile import DETAIL
from planforge.codes.uk.fixtures_profile import FIX
from planforge.drawing.model import ClearRoom, PlacedFixture, PlacedOpening
from planforge.enums import AccessStandard, Axis
from planforge.fixtures.result import KitchenAudit

SIDE_TOL_MM = DETAIL.kitchen_side_tol_mm
MIN_SEGMENT_MM = DETAIL.kitchen_min_segment_mm

OPPOSITE = ({"S", "N"}, {"W", "E"})


def _cuts_on_side(
    room: ClearRoom, openings: list[PlacedOpening], side: str
) -> list[tuple[int, int]]:
    """المقاطع المقطوعة على ضلع، بإحداثيات محلية على طول الضلع."""
    cuts: list[tuple[int, int]] = []
    for o in openings:
        # نافذة فوق المنضدة لا تقطعها
        if o.is_window and o.sill_mm >= FIX.worktop_height:
            continue
        if side in ("S", "N") and o.axis is Axis.H:
            edge = room.y if side == "S" else room.y2
            if abs(o.coord - edge) <= SIDE_TOL_MM:
                cuts.append((o.start - room.x, o.end - room.x))
        elif side in ("W", "E") and o.axis is Axis.V:
            edge = room.x if side == "W" else room.x2
            if abs(o.coord - edge) <= SIDE_TOL_MM:
                cuts.append((o.start - room.y, o.end - room.y))
    return sorted(cuts)


def _free_length(span: int, cuts: list[tuple[int, int]]) -> int:
    """طول الضلع المتاح بعد خصم المقاطع المقطوعة (تُدمج المتراكبة)."""
    total = 0
    cursor = 0
    for lo, hi in cuts:
        lo, hi = max(0, lo), min(span, hi)
        if hi <= cursor:
            continue
        total += max(0, lo - cursor)
        cursor = max(cursor, hi)
    return total + max(0, span - cursor)


SAME_WALL_TOL_MM = 200
"""سماحية اعتبار تجهيزين على ضلع واحد — تستوعب فرق سماكة الوحدات."""


def _wall_axis(f: PlacedFixture) -> str:
    """محور امتداد التجهيز على ضلعه: 'x' أو 'y'."""
    return "x" if f.rotation_deg in (0, 180) else "y"


def _along(f: PlacedFixture) -> tuple[int, int, int]:
    """
    (البداية، النهاية، إحداثي الضلع) على محور الامتداد.

    الدوران في `pack.py`: 0 = الظهر إلى الجنوب، 90 = الغرب،
    180 = الشمال، 270 = الشرق.
    """
    if f.rotation_deg == 0:
        return (f.x, f.x + f.w, f.y)
    if f.rotation_deg == 180:
        return (f.x, f.x + f.w, f.y + f.h)
    if f.rotation_deg == 90:
        return (f.y, f.y + f.h, f.x)
    return (f.y, f.y + f.h, f.x + f.w)


def _clear_beside(
    target: PlacedFixture,
    others: list[PlacedFixture],
    room: ClearRoom,
) -> tuple[int, int]:
    """
    الطول الحرّ على ضلع التجهيز يمينًا ويسارًا، محدودًا بأقرب تجهيز أو
    بحدّ الغرفة.

    هذا ما يقيسه `worktop_beside_hob_min`: مساحة إنزال القدر الساخن.
    غيابها ليس عيبًا تجميليًا — هو سبب حرائق مطابخ.
    """
    t_lo, t_hi, t_edge = _along(target)
    axis = _wall_axis(target)
    lo_bound = room.x if axis == "x" else room.y
    hi_bound = room.x2 if axis == "x" else room.y2

    for f in others:
        if f.id == target.id or _wall_axis(f) != axis:
            continue
        f_lo, f_hi, f_edge = _along(f)
        if abs(f_edge - t_edge) > SAME_WALL_TOL_MM:
            continue
        if f_hi <= t_lo:
            lo_bound = max(lo_bound, f_hi)
        elif f_lo >= t_hi:
            hi_bound = min(hi_bound, f_lo)

    return (max(0, t_lo - lo_bound), max(0, hi_bound - t_hi))


def audit_kitchen(
    room: ClearRoom,
    openings: list[PlacedOpening],
    fixtures: list[PlacedFixture],
    *,
    bedspaces: int,
    access: AccessStandard,
) -> KitchenAudit:
    problems: list[tuple[str, bool]] = []

    segments: list[tuple[str, int]] = []
    for side, span in (
        ("S", room.w), ("N", room.w), ("W", room.h), ("E", room.h)
    ):
        free = _free_length(span, _cuts_on_side(room, openings, side))
        if free >= MIN_SEGMENT_MM:
            segments.append((side, free))

    segments.sort(key=lambda s: (-s[1], s[0]))
    chosen = segments[:2]
    usable = sum(length for _side, length in chosen)
    sides = {s for s, _ in chosen}
    opposite = len(chosen) == 2 and sides in OPPOSITE
    if len(chosen) == 2 and not opposite:
        usable -= FIX.corner_loss_mm     # الزاوية تُخصم مرة واحدة
    usable = max(0, usable)

    required = FIX.worktop_required(bedspaces)
    if usable < required:
        problems.append((
            f"طول المنضدة المتاح {usable} مم دون المطلوب {required} مم "
            f"لـ{bedspaces} أشخاص",
            True,
        ))

    depth = FIX.worktop_depth
    gangway = room.min_dim - (2 * depth if opposite else depth)
    need_gang = FIX.kitchen_gangway[access]
    if gangway < need_gang:
        layout = "ضلعان متقابلان" if opposite else "ضلع واحد"
        problems.append((
            f"عرض المجاز {gangway} مم دون {need_gang} مم ({layout})",
            True,
        ))

    hob = next((f for f in fixtures if f.code == "HOB"), None)
    sink = next((f for f in fixtures if f.code == "SINK"), None)

    # ── طول المنضدة الذي تشغله الوحدات فعلًا ──
    #
    # `is_worktop` يقرأ هنا لأول مرة. الحزم لا يعرف طول الضلع المتاح —
    # يضع التجهيزات في الغرفة، لا على منضدة. فقد ينجح ترتيبٌ تتجاوز فيه
    # عروضُ الوحدات مجتمعةً الطولَ الذي بقي بعد خصم الأبواب والنوافذ.
    on_worktop = [
        f for f in fixtures
        if FIX.catalogue.get(f.code) and FIX.catalogue[f.code].is_worktop
    ]
    occupied = sum(
        max(_along(f)[1] - _along(f)[0], 0) for f in on_worktop
    )
    if occupied > usable:
        problems.append((
            f"وحدات المنضدة ({', '.join(sorted(f.code for f in on_worktop))}) "
            f"تشغل {occupied} مم من طول متاح {usable} مم",
            True,
        ))

    if hob is not None:
        hx, hy = hob.centroid
        to_corner = min(
            hx - room.x, room.x2 - hx, hy - room.y, room.y2 - hy
        )
        need_corner = FIX.hob_from_corner_min + hob.w // 2
        if to_corner < need_corner:
            problems.append((
                f"الطبّاخ أقرب من {FIX.hob_from_corner_min} مم إلى زاوية "
                f"(المقيس {to_corner} مم)",
                False,
            ))

        # منضدة الإنزال بجانب الطبّاخ — سلامة، فتُبلَّغ خطأً
        left, right = _clear_beside(hob, fixtures, room)
        if max(left, right) < FIX.worktop_beside_hob_min:
            problems.append((
                f"لا منضدة إنزال بجانب الطبّاخ: أوسع جانب "
                f"{max(left, right)} مم دون {FIX.worktop_beside_hob_min} مم",
                True,
            ))

        if sink is not None:
            sx, sy = sink.centroid
            gap = abs(hx - sx) + abs(hy - sy) - (hob.w + sink.w) // 2
            if gap < FIX.hob_to_sink_min:
                problems.append((
                    f"المنضدة الفاصلة بين الطبّاخ والحوض {max(gap, 0)} مم "
                    f"دون {FIX.hob_to_sink_min} مم",
                    False,
                ))

        if FIX.hob_under_window_forbidden:
            near = DETAIL.hob_window_proximity_mm
            for o in openings:
                if not o.is_window:
                    continue
                under = (
                    abs(o.coord - hy) < near and o.start <= hx <= o.end
                    if o.axis is Axis.H
                    else abs(o.coord - hx) < near and o.start <= hy <= o.end
                )
                if under:
                    problems.append((
                        f"الطبّاخ تحت النافذة {o.id} مباشرة", False,
                    ))
                    break

    if sink is not None:
        left, right = _clear_beside(sink, fixtures, room)
        if max(left, right) < FIX.worktop_beside_sink_min:
            problems.append((
                f"لا مصفاة بجانب الحوض: أوسع جانب {max(left, right)} مم "
                f"دون {FIX.worktop_beside_sink_min} مم",
                False,
            ))

    return KitchenAudit(
        room=room.id,
        usable_run_mm=usable,
        required_run_mm=required,
        gangway_mm=gangway,
        required_gangway_mm=need_gang,
        sides=tuple(side for side, _ in chosen),
        problems=tuple(problems),
    )
