"""
المخرج الهندسي: مستطيلات على خطوط مراكز الجدران، وفتحات مُعلنة.

لا يحتوي جدرانًا بسماكة — تلك تُشتق في `drawing/`. النموذج هنا قابل
للتغيير (غير مُجمَّد) لأن `pipeline` و`edit` يعدّلانه في مكانه.
"""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from planforge.enums import OpeningKind, RoomType
from planforge.geometry.rect import Rect


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RectModel(_Base):
    x: int
    y: int
    w: int
    h: int

    def to_rect(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)

    @classmethod
    def of(cls, r: Rect) -> RectModel:
        return cls(x=r.x, y=r.y, w=r.w, h=r.h)


class RoomInstance(_Base):
    id: str
    type: RoomType
    storey: int
    rect: RectModel
    ceiling_height_mm: int | None = None
    storage_area_mm2: int = Field(
        default=0, description="تخزين مدمج داخل الغرفة (NDSS §9)"
    )

    @property
    def r(self) -> Rect:
        return self.rect.to_rect()


class Opening(_Base):
    """
    فتحة على الحد المشترك بين غرفتين، أو على واجهة خارجية إن كانت b فارغة.

    `position_mm` مسافة مركز الفتحة من بداية الحد. المرحلة 3 تعيد حلّها
    على الجدار الحقيقي، فلا تُعتمد كموضع نهائي.
    """
    id: str
    kind: OpeningKind
    storey: int
    a: str
    b: str | None = None
    clear_width_mm: int
    clear_height_mm: int = 2040
    position_mm: int = 0
    sill_mm: int = 0
    openable_area_mm2: int = 0

    @property
    def is_external(self) -> bool:
        return self.b is None

    def rooms(self) -> tuple[str, ...]:
        return tuple(x for x in (self.a, self.b) if x)


class StoreyLayout(_Base):
    index: int
    envelope: RectModel
    rooms: list[RoomInstance] = []
    openings: list[Opening] = []
    protected_stair: bool = False

    def room(self, room_id: str) -> RoomInstance:
        for r in self.rooms:
            if r.id == room_id:
                return r
        raise KeyError(room_id)


class Layout(_Base):
    project_name: str
    engine_version: str = "0.7.0"
    seed: int = 0
    storeys: list[StoreyLayout] = []

    def storey(self, index: int) -> StoreyLayout:
        for s in self.storeys:
            if s.index == index:
                return s
        raise KeyError(index)

    def all_rooms(self) -> list[RoomInstance]:
        return [r for s in self.storeys for r in s.rooms]

    def rooms_of_type(self, *types: RoomType) -> list[RoomInstance]:
        wanted = set(types)
        return [r for r in self.all_rooms() if r.type in wanted]

    def find(self, room_id: str) -> RoomInstance:
        for r in self.all_rooms():
            if r.id == room_id:
                return r
        raise KeyError(room_id)
