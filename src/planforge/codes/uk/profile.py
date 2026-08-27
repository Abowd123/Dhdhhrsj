"""
ثوابت الكود البريطاني — معزولة عن المنطق بالكامل.

‼ كل قيمة في هذا الملف **غير مُتحقَّقة** ضد النصوص الرسمية. أُدخلت من
المعرفة العامة بالوثائق المعتمدة. قبل أي استخدام مهني تُراجع كل قيمة
مقابل الإصدار الساري وتُوقَّع — `planforge codes worksheet` هو الطريق
العملي لذلك، و`planforge codes audit` يقول ما بقي.

المراجع المُدّعاة: Approved Documents B / F / G / K / M، و
Technical Housing Standards — Nationally Described Space Standard (2015).

قاعدة صيانة: كل حقل رقمي هنا يقابله سجل إثبات في
`codes/uk/provenance_uk.py`. `test_every_code_value_has_provenance`
يفشل عند أي رقم بلا سجل، أو سجل بلا رقم — فلا يتسلّل رقم جديد بلا
مسار للمراجعة. لا تُضف رقمًا هنا بلا سجل هناك.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from planforge.enums import AccessStandard, RoomType
from planforge.units import m, m2

# ─────────────── NDSS جدول 1 ───────────────
# (عدد الأسرّة، غرف النوم، {عدد الأدوار: GIA بالمتر المربع})
# المفتاح النصّي "4p2b/1s" يجعل كل صف قابلًا للتوقيع وحده — وهذه هي
# الحبيبة التي يراجع بها المهندس جدولًا: صفًّا صفًّا لا جدولًا جملةً.
_NDSS_RAW: tuple[tuple[int, int, dict[int, float]], ...] = (
    (1, 1, {1: 39.0}),
    (2, 1, {1: 50.0}),
    (2, 2, {1: 58.0, 2: 70.0}),
    (3, 2, {1: 61.0, 2: 70.0}),
    (4, 2, {1: 70.0, 2: 79.0}),
    (4, 3, {1: 74.0, 2: 84.0, 3: 90.0}),
    (5, 3, {1: 86.0, 2: 93.0, 3: 99.0}),
    (6, 3, {1: 95.0, 2: 102.0, 3: 108.0}),
    (5, 4, {2: 90.0, 3: 97.0}),
    (6, 4, {2: 99.0, 3: 106.0}),
    (7, 4, {2: 108.0, 3: 115.0}),
    (8, 4, {2: 117.0, 3: 124.0}),
)


def gia_key(bedspaces: int, bedrooms: int, storeys: int) -> str:
    return f"{bedspaces}p{bedrooms}b/{storeys}s"


def _gia_table() -> dict[str, int]:
    out: dict[str, int] = {}
    for people, beds, by_storeys in _NDSS_RAW:
        for storeys, gia in by_storeys.items():
            out[gia_key(people, beds, storeys)] = m2(gia)
    return out


def _parse_key(key: str) -> tuple[int, int, int]:
    head, tail = key.split("/")
    people, beds = head.split("p")
    return (int(people), int(beds.rstrip("b")), int(tail.rstrip("s")))


@dataclass(frozen=True)
class UKCodeProfile:
    edition: str = "2023-01 (غير مُتحقَّق — يلزم توقيع مهندس)"
    verified_by: str = ""

    # ─────────── NDSS 2015 ───────────
    ndss_gia_table: dict[str, int] = field(default_factory=_gia_table)
    bedroom_min_area: dict[RoomType, int] = field(default_factory=lambda: {
        RoomType.BEDROOM_SINGLE: m2(7.5),
        RoomType.BEDROOM_DOUBLE: m2(11.5),
        RoomType.BEDROOM_MAIN: m2(11.5),
    })
    bedroom_min_width: dict[RoomType, int] = field(default_factory=lambda: {
        RoomType.BEDROOM_SINGLE: m(2.15),
        RoomType.BEDROOM_DOUBLE: m(2.55),
        RoomType.BEDROOM_MAIN: m(2.75),
    })
    storage_by_bedrooms: dict[int, int] = field(default_factory=lambda: {
        1: m2(1.0), 2: m2(1.5), 3: m2(2.0),
        4: m2(2.5), 5: m2(3.0), 6: m2(3.5),
    })
    ceiling_min_height: int = m(2.30)
    ceiling_min_coverage: float = 0.75

    # ─────────── Approved Document K ───────────
    stair_max_rise: int = 220
    stair_min_going: int = 220
    stair_max_pitch_deg: float = 42.0
    stair_2r_plus_g: tuple[int, int] = (550, 700)
    stair_min_headroom: int = m(2.00)
    stair_min_width: int = m(0.90)   # ليس مفروضًا للسلالم الخاصة؛ عرف عملي

    # ─────────── Approved Document M ───────────
    corridor_min_width: dict[AccessStandard, int] = field(
        default_factory=lambda: {
            AccessStandard.M4_1: m(0.90),
            AccessStandard.M4_2: m(1.05),
            AccessStandard.M4_3: m(1.20),
        }
    )
    door_min_clear_width: dict[AccessStandard, int] = field(
        default_factory=lambda: {
            AccessStandard.M4_1: 750,
            AccessStandard.M4_2: 800,
            AccessStandard.M4_3: 850,
        }
    )
    door_side_nib: int = 300
    wc_at_entrance_storey_required: bool = True

    # ─────────── Approved Document F ───────────
    purge_vent_ratio: float = 1 / 20
    extract_rates_ls: dict[RoomType, int] = field(default_factory=lambda: {
        RoomType.KITCHEN: 30,
        RoomType.KITCHEN_DINING: 30,
        RoomType.UTILITY: 30,
        RoomType.BATHROOM: 15,
        RoomType.SHOWER_ROOM: 15,
        RoomType.ENSUITE: 15,
        RoomType.WC: 6,
    })

    # ─────────── Approved Document B Vol 1 ───────────
    protected_stair_threshold: int = m(4.5)
    alt_escape_threshold: int = m(7.5)
    escape_window_min_area: int = m2(0.33)
    escape_window_min_dim: int = 450
    escape_window_sill_range: tuple[int, int] = (800, 1100)
    fire_door_rating_minutes: int = 30

    # ─────────── Approved Document G ───────────
    wc_needs_lobby_to_kitchen: bool = True

    # ─────────── عرف مهني — لا نص قانوني ───────────
    practical_min_width: dict[RoomType, int] = field(default_factory=lambda: {
        RoomType.WC: 800,
        RoomType.ENSUITE: m(1.20),
        RoomType.BATHROOM: m(1.70),
        RoomType.SHOWER_ROOM: m(1.20),
        RoomType.KITCHEN: m(2.40),
        RoomType.KITCHEN_DINING: m(2.80),
        RoomType.LIVING: m(3.00),
        RoomType.DINING: m(2.60),
        RoomType.MAJLIS: m(3.20),
        RoomType.STUDY: m(2.10),
        RoomType.UTILITY: m(1.60),
        RoomType.STORAGE: 600,
        RoomType.HALL: m(0.90),
        RoomType.LANDING: m(0.90),
        RoomType.ENTRANCE_HALL: m(1.20),
        RoomType.LOBBY: m(0.90),
        RoomType.STAIR: m(0.90),
        RoomType.PLANT: 700,
        RoomType.GARAGE: m(2.40),
        RoomType.BEDROOM_SINGLE: m(2.15),
        RoomType.BEDROOM_DOUBLE: m(2.55),
        RoomType.BEDROOM_MAIN: m(2.75),
    })
    max_aspect_default: float = 2.2

    # ─────────── مشتقات ───────────

    @property
    def fire_door_label(self) -> str:
        return f"FD{self.fire_rating_minutes_int}"

    @property
    def fire_rating_minutes_int(self) -> int:
        return int(self.fire_door_rating_minutes)

    def ndss_gia(
        self, bedspaces: int, bedrooms: int, storeys: int
    ) -> int | None:
        """
        أصغر GIA يكفي لهذا التركيب.

        المنطق: نقبل أي صفّ بعدد غرف النوم نفسه وعدد أسرّة ≥ المطلوب، ثم
        نأخذ أصغر GIA. الصفّ بعدد أدوار مطابق أولًا، وإلا فأقرب عدد أعلى
        (الأدوار الأكثر تفرض GIA أكبر، فالاختيار متحفّظ).
        """
        best: int | None = None
        rows: dict[tuple[int, int], dict[int, int]] = {}
        for key, gia in self.ndss_gia_table.items():
            people, beds, st = _parse_key(key)
            rows.setdefault((people, beds), {})[st] = gia
        for (people, beds), by_storeys in rows.items():
            if beds != bedrooms or people < bedspaces:
                continue
            gia = by_storeys.get(storeys)
            if gia is None:
                higher = [s for s in by_storeys if s >= storeys]
                gia = by_storeys[min(higher)] if higher else \
                    by_storeys[max(by_storeys)]
            if best is None or gia < best:
                best = gia
        return best

    def storage_required(self, bedrooms: int) -> int:
        if not self.storage_by_bedrooms:
            return 0
        keys = sorted(self.storage_by_bedrooms)
        for k in keys:
            if bedrooms <= k:
                return self.storage_by_bedrooms[k]
        return self.storage_by_bedrooms[keys[-1]]


UK = UKCodeProfile()
