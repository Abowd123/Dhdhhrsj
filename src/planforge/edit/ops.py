"""
عمليات التعديل.

كلها تحفظ الطوبولوجيا: لا عملية تُنشئ غرفة أو تحذفها. هذا ما يجعل
التعديل محلّيًا ومتوقَّعًا — إنشاء غرفة يقتضي إعادة تبليط، أي إعادة
تشغيل المُحلّل، أي مخططًا مختلفًا بلا صلة بما كان على الشاشة.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class _Op(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    storey: int = 0


class MoveWall(_Op):
    """تحريك خط جدار. الغرف المرتبطة به تتبعه، فيبقى التبليط تامًا."""
    kind: Literal["move_wall"] = "move_wall"
    line: str
    coord_mm: int


class ResizeRoom(_Op):
    """
    مساحة مستهدفة جديدة لغرفة.

    ليست فرضًا: المُحلّل يقرّبها ما أمكن مع حفظ الأبعاد الدنيا لكل
    الغرف الأخرى، فقد تصل إلى غير المطلوب بالضبط.
    """
    kind: Literal["resize_room"] = "resize_room"
    room: str
    target_area_mm2: int = Field(gt=0)


class SwapRooms(_Op):
    """
    تبادل بصمتَي غرفتين.

    أضعف العمليات: تبادل بصمتين مختلفتي الأبعاد يكسر التبليط، فتُعاد
    الطوبولوجيا ثم يُعاد الحل. ينجح بين غرفتين متقاربتي الحجم، ويُرفض
    غالبًا فيما دون ذلك — وإعادة التوليد أجدى.
    """
    kind: Literal["swap_rooms"] = "swap_rooms"
    a: str
    b: str


class SetRoomType(_Op):
    """
    تغيير نوع غرفة.

    يغيّر حدودها الدنيا وطقم تجهيزاتها معًا، فيُعاد الحل بعده: غرفة
    مخزن تصير غرفة نوم قد لا تستوعب حدها الجديد.
    """
    kind: Literal["set_room_type"] = "set_room_type"
    room: str
    room_type: str


class MoveOpening(_Op):
    kind: Literal["move_opening"] = "move_opening"
    opening: str
    position_mm: int


class SetOpeningWidth(_Op):
    kind: Literal["set_opening_width"] = "set_opening_width"
    opening: str
    clear_width_mm: int = Field(gt=0)


class FlipOpening(_Op):
    """عكس موضع الفتحة على جدارها (يمين ↔ يسار)."""
    kind: Literal["flip_opening"] = "flip_opening"
    opening: str


Operation = (
    MoveWall | ResizeRoom | SwapRooms | SetRoomType
    | MoveOpening | SetOpeningWidth | FlipOpening
)

OP_TYPES: dict[str, type[_Op]] = {
    "move_wall": MoveWall,
    "resize_room": ResizeRoom,
    "swap_rooms": SwapRooms,
    "set_room_type": SetRoomType,
    "move_opening": MoveOpening,
    "set_opening_width": SetOpeningWidth,
    "flip_opening": FlipOpening,
}

GEOMETRY_OPS = frozenset({
    "move_wall", "resize_room", "swap_rooms", "set_room_type",
})
"""العمليات التي تُعيد حل الخطوط — الباقي يمسّ الفتحات وحدها."""


def parse_op(raw: dict) -> Operation:
    kind = raw.get("kind")
    if kind not in OP_TYPES:
        known = ", ".join(sorted(OP_TYPES))
        raise ValueError(
            f"عملية غير معروفة: {kind!r} — المعروف: {known}"
        )
    return OP_TYPES[kind].model_validate(raw)
