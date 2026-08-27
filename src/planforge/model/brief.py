"""
المتطلب: المدخل الوحيد للنظام.

Brief + seed + إصدار المحرك = مخطط قابل لإعادة الإنتاج بالتمام.

قيد يستحق الذكر هنا لا في المُحلّل فقط: التبليط تام، فمجموع مساحات
الغرف لكل دور **يساوي** مساحة `build_envelope` ولا يقاربه. فرقٌ بـ10 م²
يُخرج INFEASIBLE بلا سبب مفهوم. `planforge diagnose --fast` يقيسه.
"""
from __future__ import annotations
from pydantic import (
    BaseModel, ConfigDict, Field, field_validator, model_validator,
)
from planforge.enums import (
    AccessStandard, BEDROOMS, MajlisMode, RelationKind, RoomType, Side,
)
from planforge.geometry.rect import Rect

DEFAULT_FLOOR_TO_FLOOR_MM = 2800
MAX_MODELLED_STOREYS = 4


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Plot(_Base):
    """أبعاد الأرض بالملّيمتر."""
    width_mm: int = Field(gt=0, description="العرض على الشارع")
    depth_mm: int = Field(gt=0)


class Setbacks(_Base):
    """الارتدادات بالملّيمتر لكل جهة."""
    front_mm: int = 0
    rear_mm: int = 0
    left_mm: int = 0
    right_mm: int = 0


class WallSpec(_Base):
    """
    سماكات الجدران. الافتراضات عرف بريطاني حديث: خارجي 300 =
    102.5 طوب + ~100 عزل/فراغ + 100 بلوك، زائد التجليط.
    """
    external_mm: int = 300
    party_mm: int = 300
    internal_loadbearing_mm: int = 125
    internal_partition_mm: int = 100


class StoreySpec(_Base):
    index: int = Field(ge=0, description="0 = دور الدخول")
    floor_level_mm: int = Field(
        ge=0, description="منسوب الأرضية فوق منسوب الأرض الخارجي"
    )
    floor_to_ceiling_mm: int = 2500
    floor_structure_mm: int = 300

    @property
    def floor_to_floor_mm(self) -> int:
        return self.floor_to_ceiling_mm + self.floor_structure_mm


class RoomRequirement(_Base):
    id: str
    type: RoomType
    target_area_mm2: int = Field(gt=0)
    min_area_mm2: int | None = None
    max_area_mm2: int | None = None
    storey: int | None = Field(default=None, description="تثبيت على دور معيّن")
    min_width_mm: int | None = None
    max_aspect: float | None = None
    requires_external_wall: bool | None = Field(
        default=None, description="افتراضيًا يُستنتج من النوع"
    )
    access_via: str | None = Field(
        default=None,
        description="الوصول عبر غرفة مضيفة بدل الحركة — غرفة داخلية بمفهوم "
                    "ADB §2.6",
    )
    fixed_rect_mm: tuple[int, int, int, int] | None = Field(
        default=None, description="(x, y, w, h) — تثبيت هندسي كامل"
    )
    note: str = Field(
        default="", description="تعليق للمستخدم، لا يقرأه المحرك"
    )

    @model_validator(mode="after")
    def _check_bounds(self) -> RoomRequirement:
        lo = self.min_area_mm2 or 0
        hi = self.max_area_mm2 or self.target_area_mm2 * 10
        if not (lo <= self.target_area_mm2 <= hi):
            raise ValueError(f"{self.id}: المساحة المستهدفة خارج المجال")
        if self.access_via == self.id:
            raise ValueError(f"{self.id}: access_via يشير إلى الغرفة نفسها")
        return self


class Relation(_Base):
    kind: RelationKind
    a: str
    b: str
    weight: int = Field(
        default=10, description="وزن التفضيل إن لم تكن قيدًا صلبًا"
    )
    hard: bool = True


class CodeProfileRef(_Base):
    jurisdiction: str = "UK"
    edition: str = "2023-01"


class Brief(_Base):
    project_name: str
    plot: Plot
    setbacks: Setbacks = Setbacks()
    street_side: Side = Side.SOUTH
    north_angle_deg: float = Field(default=0.0, ge=0, lt=360)

    storeys: tuple[StoreySpec, ...]
    rooms: tuple[RoomRequirement, ...]
    relations: tuple[Relation, ...] = ()

    bedspaces: int = Field(
        gt=0, description="عدد الأشخاص — يحدد GIA في NDSS"
    )
    access_standard: AccessStandard = AccessStandard.M4_1
    walls: WallSpec = WallSpec()
    code: CodeProfileRef = CodeProfileRef()
    majlis_mode: MajlisMode = MajlisMode.NONE

    seed: int = 0

    # ─────────────── المُحوِّلات ───────────────

    @field_validator("storeys", mode="before")
    @classmethod
    def _coerce_storeys(cls, v: object) -> object:
        """
        يقبل:
            storeys: 1          → دور واحد
            storeys: 3          → ثلاثة أدوار بمناسيب افتراضية
            storeys: [ {...} ]  → مواصفات مفصّلة

        دور واحد حالة مدعومة من الدرجة الأولى: تُتجاوز النواة الرأسية
        والسلالم ونوافذ الهروب والمحاذاة بشرط صريح لا بالمصادفة.
        """
        if isinstance(v, bool):
            raise ValueError("storeys لا يقبل قيمة منطقية")
        if isinstance(v, int):
            if v < 1:
                raise ValueError("عدد الأدوار يجب أن يكون ≥ 1")
            if v > MAX_MODELLED_STOREYS:
                raise ValueError(
                    f"أكثر من {MAX_MODELLED_STOREYS} أدوار يتطلب مساري هروب "
                    f"ونظام رشاشات — غير مُنمذَج"
                )
            return tuple(
                StoreySpec(
                    index=i, floor_level_mm=i * DEFAULT_FLOOR_TO_FLOOR_MM
                )
                for i in range(v)
            )
        return v

    # ─────────────── المشتقات ───────────────

    @property
    def build_envelope(self) -> Rect:
        """
        مظروف البناء = الأرض ناقص الارتدادات.

        هذا هو المظروف الذي يعمل عليه المُحلّل، ومستطيلاته **خطوط مراكز**
        جدران لا أوجهًا داخلية. طبقة الرسم تُزيح بنصف السماكة، فتنكمش
        المساحات الصافية 4–8% — و`pipeline.py` يعوّضها بحلقة قياس.
        """
        s = self.setbacks
        return Rect(
            x=s.left_mm,
            y=s.front_mm,
            w=self.plot.width_mm - s.left_mm - s.right_mm,
            h=self.plot.depth_mm - s.front_mm - s.rear_mm,
        )

    @property
    def n_storeys(self) -> int:
        return len(self.storeys)

    @property
    def is_multi_storey(self) -> bool:
        return len(self.storeys) > 1

    @property
    def entrance_storey(self) -> int:
        return min(s.index for s in self.storeys)

    @property
    def top_storey(self) -> int:
        return max(s.index for s in self.storeys)

    @property
    def n_bedrooms(self) -> int:
        return sum(1 for r in self.rooms if r.type in BEDROOMS)

    @property
    def top_floor_level_mm(self) -> int:
        return max(s.floor_level_mm for s in self.storeys)

    @property
    def max_floor_to_floor_mm(self) -> int:
        ordered = sorted(self.storeys, key=lambda s: s.index)
        if len(ordered) < 2:
            return 0
        return max(
            b.floor_level_mm - a.floor_level_mm
            for a, b in zip(ordered, ordered[1:])
        )

    def room(self, room_id: str) -> RoomRequirement:
        for r in self.rooms:
            if r.id == room_id:
                return r
        raise KeyError(room_id)

    def storey_spec(self, index: int) -> StoreySpec:
        for s in self.storeys:
            if s.index == index:
                return s
        raise KeyError(index)

    def rooms_of_storey(self, index: int) -> tuple[RoomRequirement, ...]:
        return tuple(r for r in self.rooms if r.storey == index)

    # ─────────────── السلامة ───────────────

    @model_validator(mode="after")
    def _check_integrity(self) -> Brief:
        ids = [r.id for r in self.rooms]
        if len(ids) != len(set(ids)):
            raise ValueError("معرّفات غرف مكررة")

        idxs = sorted(s.index for s in self.storeys)
        if idxs != list(range(len(idxs))):
            raise ValueError("أرقام الأدوار يجب أن تكون 0..n-1 متصلة")

        if len(self.storeys) > MAX_MODELLED_STOREYS:
            raise ValueError(
                f"أكثر من {MAX_MODELLED_STOREYS} أدوار يتطلب مساري هروب "
                f"ونظام رشاشات — غير مُنمذَج"
            )

        known = set(ids)
        valid_storeys = {s.index for s in self.storeys}
        for r in self.rooms:
            if r.storey is not None and r.storey not in valid_storeys:
                raise ValueError(f"{r.id}: رقم دور غير موجود ({r.storey})")
            if r.access_via and r.access_via not in known:
                raise ValueError(
                    f"{r.id}: access_via يشير إلى غرفة غير معرّفة "
                    f"({r.access_via})"
                )

        for rel in self.relations:
            for rid in (rel.a, rel.b):
                if rid not in known:
                    raise ValueError(f"علاقة تشير إلى غرفة غير معرّفة: {rid}")

        env = self.build_envelope
        if env.w <= 0 or env.h <= 0:
            raise ValueError("الارتدادات تستهلك الأرض بالكامل")

        if not self.is_multi_storey:
            for r in self.rooms:
                if r.type is RoomType.STAIR:
                    raise ValueError(
                        f"{r.id}: سلّم في مبنى بدور واحد — احذفه أو زد عدد "
                        f"الأدوار"
                    )
        return self
