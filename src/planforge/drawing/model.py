"""
نموذج الرسم: الطبقة الوحيدة التي تُصدَّر. تحتوي هندسة قابلة للبناء.

الفرق الجوهري عن `model/layout.py`: هناك مستطيلات على خطوط المراكز،
وهنا جدران بسماكاتها وفتحات مقطوعة فيها وغرف بأبعادها **الصافية** بين
الأوجه. الأبعاد الصافية هي الأساس القانوني للقياس في NDSS و ADM، فكل
حكم في `rules/drawing_rules.py` يُقاس عليها.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from planforge.enums import Axis, OpeningKind, RoomType


class WallKind(StrEnum):
    EXTERNAL = "external"
    PARTY = "party"
    LOADBEARING = "loadbearing"
    PARTITION = "partition"
    FIRE = "fire"           # محيط السلّم المحمي — ADB para 2.6


WALL_LAYER: dict[WallKind, str] = {
    WallKind.EXTERNAL: "A-WALL",
    WallKind.PARTY: "A-WALL-PRTY",
    WallKind.LOADBEARING: "A-WALL",
    WallKind.PARTITION: "A-WALL-INTR",
    WallKind.FIRE: "A-WALL-FIRE",
}


@dataclass(frozen=True, slots=True)
class WallFace:
    """
    مقطع حدود بين غرفتين، أو بين غرفة والخارج، مصنَّفًا بسماكته.

    الوحدة الذرّية التي تُحمَل عليها الفتحات، لأنها وحدها تعرف أي
    غرفتين تفصل — وهذا شرط اختيار جهة دوران الباب وتصنيفه.
    """
    axis: Axis
    coord: int
    lo: int
    hi: int
    a: str | None       # الجهة الدنيا (يسار/أسفل)، None = الخارج
    b: str | None       # الجهة العليا (يمين/أعلى)، None = الخارج
    kind: WallKind
    thickness_mm: int

    @property
    def length(self) -> int:
        return self.hi - self.lo

    @property
    def is_external(self) -> bool:
        return self.a is None or self.b is None

    def rooms(self) -> frozenset[str]:
        return frozenset(x for x in (self.a, self.b) if x)


@dataclass(frozen=True, slots=True)
class WallRun:
    """مقاطع متصلة مدموجة على نفس الخط وبنفس النوع — كيان الرسم."""
    id: str
    axis: Axis
    coord: int
    lo: int
    hi: int
    kind: WallKind
    thickness_mm: int
    faces: tuple[WallFace, ...]

    @property
    def length(self) -> int:
        return self.hi - self.lo

    def rooms(self) -> frozenset[str]:
        return frozenset(r for f in self.faces for r in f.rooms())

    def band(self) -> tuple[int, int, int, int]:
        """نطاق الجدار (x, y, w, h) — خط المركز مُزاح بنصف السماكة."""
        t = self.thickness_mm
        if self.axis is Axis.V:
            return (self.coord - t // 2, self.lo, t, self.hi - self.lo)
        return (self.lo, self.coord - t // 2, self.hi - self.lo, t)

    def contains_span(self, lo: int, hi: int) -> bool:
        return self.lo <= lo and hi <= self.hi


@dataclass(frozen=True, slots=True)
class PlacedOpening:
    """فتحة محلولة هندسيًا على جدار: موضع مطلق، جهة، اتجاه فتح."""
    id: str
    kind: OpeningKind
    axis: Axis
    coord: int              # إحداثي خط مركز الجدار
    start: int              # بداية الفتحة على طول الجدار
    clear_width_mm: int
    thickness_mm: int
    head_mm: int
    sill_mm: int
    room_a: str
    room_b: str | None
    swing_to: str | None    # الغرفة التي يفتح إليها الباب
    swing_positive: bool = True
    """
    هل يفتح الباب نحو الاتجاه الموجب للمحور العمودي على الجدار؟

    يُحسب في `place_openings` بمقارنة مركز غرفة `swing_to` بإحداثي
    الفتحة. يُستخدم في رسم ربع الدائرة (DXF و SVG) وفي حساب مربع الدوران
    في تدقيق التجهيزات. افتراضٌ ثابت هنا يُظهر أبوابًا تفتح في جدار.
    """
    hinge_left: bool = True
    openable_area_mm2: int = 0
    fire_rating: str = ""   # "FD30" أو ""

    @property
    def end(self) -> int:
        return self.start + self.clear_width_mm

    @property
    def mid(self) -> int:
        return self.start + self.clear_width_mm // 2

    @property
    def is_door(self) -> bool:
        return self.kind in {OpeningKind.DOOR, OpeningKind.FIRE_DOOR}

    @property
    def is_window(self) -> bool:
        return self.kind in {OpeningKind.WINDOW, OpeningKind.ESCAPE_WINDOW}

    def rooms(self) -> tuple[str, ...]:
        return tuple(x for x in (self.room_a, self.room_b) if x)

    def insert_point(self) -> tuple[int, int]:
        """نقطة مفصلة الباب — أصل بلوك الباب في التصدير."""
        if self.axis is Axis.V:
            return (self.coord, self.start if self.hinge_left else self.end)
        return (self.start if self.hinge_left else self.end, self.coord)

    def rotation_deg(self) -> float:
        if self.axis is Axis.V:
            base = 90.0 if self.hinge_left else 270.0
        else:
            base = 0.0 if self.hinge_left else 180.0
        if not self.swing_positive:
            base = (base + 180.0) % 360.0
        return base


@dataclass(frozen=True, slots=True)
class ClearRoom:
    """الغرفة بأبعادها الصافية بين أوجه الجدران — الأساس القانوني للقياس."""
    id: str
    type: RoomType
    x: int
    y: int
    w: int
    h: int
    centerline_area_mm2: int
    ceiling_height_mm: int = 0
    storage_area_mm2: int = 0

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def min_dim(self) -> int:
        return min(self.w, self.h)

    @property
    def centroid(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def shrink_ratio(self) -> float:
        """المساحة الصافية ÷ مساحة خط المركز. 1.0 يعني بلا جدران."""
        if not self.centerline_area_mm2:
            return 0.0
        return self.area / self.centerline_area_mm2

    def contains_point(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x2 and self.y <= py <= self.y2


@dataclass(frozen=True, slots=True)
class PlacedFixture:
    """
    تجهيز محلول: بصمة الجسم + حيّز الاستخدام أمامه.

    rotation 0 = الظهر إلى الجدار الجنوبي، الواجهة شمالًا.
    """
    id: str
    code: str
    room: str
    x: int
    y: int
    w: int
    h: int
    rotation_deg: int
    activity: tuple[int, int, int, int]   # (x, y, w, h) مطلق

    @property
    def centroid(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def body(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


@dataclass(frozen=True, slots=True)
class StairDraw:
    """
    هندسة السلّم للرسم.

    الحقول صريحة قصدًا: النسخة السابقة كانت `tuple[int, ...]` يفهمها
    مُصدِّر DXF مواضعَ قوائم ومُصدِّر SVG مستطيلًا، فرسم أحدهما خطأً.
    """
    room: str
    rect: tuple[int, int, int, int]      # المستطيل الصافي
    risers: tuple[int, ...]              # مواضع خطوط القوائم (مطلقة)
    horizontal: bool                     # مجرى السلّم على المحور x؟
    n_risers: int = 0
    rise_mm: float = 0.0
    going_mm: int = 0


@dataclass(frozen=True, slots=True)
class DimChain:
    axis: Axis          # V = سلسلة تقيس مسافات رأسية
    base: int           # إحداثي خط الأبعاد
    ticks: tuple[int, ...]
    tag: str


@dataclass(frozen=True, slots=True)
class Label:
    text: str
    point: tuple[int, int]
    layer: str
    height_mm: int = 250
    arabic: bool = False


@dataclass
class StoreyDrawing:
    index: int
    envelope: tuple[int, int, int, int]
    runs: list[WallRun] = field(default_factory=list)
    faces: list[WallFace] = field(default_factory=list)
    openings: list[PlacedOpening] = field(default_factory=list)
    rooms: list[ClearRoom] = field(default_factory=list)
    fixtures: list[PlacedFixture] = field(default_factory=list)
    fixture_failures: list[str] = field(default_factory=list)
    dims: list[DimChain] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    protected_stair: bool = False
    stair: StairDraw | None = None

    def room(self, rid: str) -> ClearRoom:
        for r in self.rooms:
            if r.id == rid:
                return r
        raise KeyError(rid)

    def opening(self, oid: str) -> PlacedOpening:
        for o in self.openings:
            if o.id == oid:
                return o
        raise KeyError(oid)

    def fixtures_of(self, room_id: str) -> list[PlacedFixture]:
        return [f for f in self.fixtures if f.room == room_id]

    def openings_of(self, room_id: str) -> list[PlacedOpening]:
        return [o for o in self.openings if room_id in o.rooms()]

    def run_carrying(self, o: PlacedOpening) -> WallRun | None:
        for r in self.runs:
            if (r.axis is o.axis and r.coord == o.coord
                    and r.contains_span(o.start, o.end)):
                return r
        return None

    @property
    def gia_mm2(self) -> int:
        """
        المساحة الداخلية الإجمالية: مساحة المظروف بعد خصم الجدار الخارجي.

        `build_drawing` يضع في `envelope` المظروف الداخلي (بين الأوجه)،
        فهذا القياس صافٍ لا على خطوط المراكز.
        """
        _x, _y, w, h = self.envelope
        return w * h


@dataclass
class Drawing:
    project_name: str
    engine_version: str
    scale_denominator: int = 100
    storeys: list[StoreyDrawing] = field(default_factory=list)

    def storey(self, index: int) -> StoreyDrawing:
        for s in self.storeys:
            if s.index == index:
                return s
        raise KeyError(index)

    @property
    def total_gia_mm2(self) -> int:
        return sum(s.gia_mm2 for s in self.storeys)

    @property
    def all_fixture_failures(self) -> list[str]:
        return [m for s in self.storeys for m in s.fixture_failures]
