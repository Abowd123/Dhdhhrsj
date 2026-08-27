"""
سلاسل الأبعاد والمسميات.

الأبعاد كيانات قابلة للتحديث في CAD لا نصوصًا ثابتة: سحب الجدار يحدّث
القياس. ثلاث سلاسل على الجهة الجنوبية والغربية — الفتحات، خطوط الجدران،
البعد الكلي — وهذا العرف المعماري القياسي.
"""
from __future__ import annotations
from planforge.codes.uk.detail_profile import DETAIL
from planforge.drawing.model import (
    Axis, ClearRoom, DimChain, Label, PlacedOpening, WallRun,
)
from planforge.enums import RoomType
from planforge.geometry.rect import Rect
from planforge.units import area_m2, to_m

DIM_OFFSET_1 = 900     # سلسلة الفتحات
DIM_OFFSET_2 = 1900    # سلسلة خطوط الجدران
DIM_OFFSET_3 = 2900    # البعد الكلي
MIN_DIM_SPAN_MM = DETAIL.dim_min_span_mm   # لا نُبعِد مسافات أقصر — تتراكم نصوصها فتُقرأ خطأً

AR_NAME: dict[RoomType, str] = {
    RoomType.ENTRANCE_HALL: "ردهة الدخول",
    RoomType.HALL: "ممر",
    RoomType.LANDING: "بسطة",
    RoomType.STAIR: "سلّم",
    RoomType.LOBBY: "ردهة",
    RoomType.LIVING: "معيشة",
    RoomType.DINING: "طعام",
    RoomType.KITCHEN: "مطبخ",
    RoomType.KITCHEN_DINING: "مطبخ وطعام",
    RoomType.STUDY: "مكتب",
    RoomType.BEDROOM_MAIN: "نوم رئيسية",
    RoomType.BEDROOM_DOUBLE: "نوم مزدوجة",
    RoomType.BEDROOM_SINGLE: "نوم فردية",
    RoomType.MAJLIS: "مجلس",
    RoomType.BATHROOM: "حمام",
    RoomType.SHOWER_ROOM: "دورة استحمام",
    RoomType.ENSUITE: "حمام ملحق",
    RoomType.WC: "دورة مياه",
    RoomType.UTILITY: "غرفة خدمة",
    RoomType.STORAGE: "مخزن",
    RoomType.PLANT: "غرفة معدات",
    RoomType.GARAGE: "مرآب",
}

EN_NAME: dict[RoomType, str] = {
    RoomType.ENTRANCE_HALL: "ENTRANCE HALL",
    RoomType.HALL: "HALL",
    RoomType.LANDING: "LANDING",
    RoomType.STAIR: "STAIR",
    RoomType.LOBBY: "LOBBY",
    RoomType.LIVING: "LIVING",
    RoomType.DINING: "DINING",
    RoomType.KITCHEN: "KITCHEN",
    RoomType.KITCHEN_DINING: "KITCHEN / DINING",
    RoomType.STUDY: "STUDY",
    RoomType.BEDROOM_MAIN: "BEDROOM 1",
    RoomType.BEDROOM_DOUBLE: "BEDROOM",
    RoomType.BEDROOM_SINGLE: "BEDROOM",
    RoomType.MAJLIS: "MAJLIS",
    RoomType.BATHROOM: "BATHROOM",
    RoomType.SHOWER_ROOM: "SHOWER RM",
    RoomType.ENSUITE: "EN-SUITE",
    RoomType.WC: "WC",
    RoomType.UTILITY: "UTILITY",
    RoomType.STORAGE: "STORE",
    RoomType.PLANT: "PLANT",
    RoomType.GARAGE: "GARAGE",
}


def room_name(rtype: RoomType, arabic: bool) -> str:
    table = AR_NAME if arabic else EN_NAME
    return table.get(rtype, str(rtype))


def _chain(
    axis: Axis, base: int, ticks: list[int], lo: int, hi: int, tag: str
) -> DimChain:
    pts = sorted(set(ticks) | {lo, hi})
    kept = [pts[0]]
    for p in pts[1:]:
        if p - kept[-1] >= MIN_DIM_SPAN_MM:
            kept.append(p)
    if kept[-1] != pts[-1]:
        kept[-1] = pts[-1]
    return DimChain(axis, base, tuple(kept), tag)


def build_dims(
    env: Rect, runs: list[WallRun], openings: list[PlacedOpening]
) -> list[DimChain]:
    wall_x = sorted({r.coord for r in runs if r.axis is Axis.V})
    wall_y = sorted({r.coord for r in runs if r.axis is Axis.H})
    op_x = sorted(
        {o.start for o in openings if o.axis is Axis.H}
        | {o.end for o in openings if o.axis is Axis.H}
    )
    op_y = sorted(
        {o.start for o in openings if o.axis is Axis.V}
        | {o.end for o in openings if o.axis is Axis.V}
    )

    chains = [
        _chain(Axis.H, env.y - DIM_OFFSET_1, op_x, env.x, env.x2,
               "S-openings"),
        _chain(Axis.H, env.y - DIM_OFFSET_2, wall_x, env.x, env.x2,
               "S-walls"),
        _chain(Axis.H, env.y - DIM_OFFSET_3, [], env.x, env.x2,
               "S-overall"),
        _chain(Axis.V, env.x - DIM_OFFSET_1, op_y, env.y, env.y2,
               "W-openings"),
        _chain(Axis.V, env.x - DIM_OFFSET_2, wall_y, env.y, env.y2,
               "W-walls"),
        _chain(Axis.V, env.x - DIM_OFFSET_3, [], env.y, env.y2,
               "W-overall"),
    ]
    return [c for c in chains if len(c.ticks) >= 2]


def build_labels(rooms: list[ClearRoom], arabic: bool) -> list[Label]:
    """
    ثلاثة أسطر لكل غرفة: الاسم، المساحة الصافية، الأبعاد.

    المساحة المكتوبة صافية لا على خطوط المراكز — الرقم الذي يُحتجّ به
    أمام السلطة الرقابية.
    """
    out: list[Label] = []
    for r in rooms:
        cx, cy = r.centroid
        base = min(300, max(150, r.min_dim // 9))
        out.append(Label(
            room_name(r.type, arabic), (cx, cy + base),
            "A-AREA-IDEN", base, arabic,
        ))
        out.append(Label(
            f"{area_m2(r.area):.2f} م²" if arabic
            else f"{area_m2(r.area):.2f} m2",
            (cx, cy - int(base * 0.4)), "A-AREA-IDEN",
            int(base * 0.82), arabic,
        ))
        out.append(Label(
            f"{to_m(r.w):.2f} x {to_m(r.h):.2f}",
            (cx, cy - int(base * 1.7)), "A-ANNO-TEXT",
            int(base * 0.74), False,
        ))
    return out
