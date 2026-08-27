"""
أبعاد التجهيزات وحيّزات استخدامها.

‼ كل رقم هنا غير مُتحقَّق ضد نص رسمي. المراجع المُدّعاة: Approved
Document M Vol 1 (رسومات الخلوص)، BS 6465-2 (تخطيط الأدوات الصحية)،
وعرف الإسكان البريطاني لأطوال مناضد المطبخ.

هذا الملف **أخطر من `profile.py` عمليًا**: أرقامه لا تُستخدم في التدقيق
فقط، بل تُستنبط منها الأبعاد الدنيا التي تُغذّي المُحلّل رجوعًا. رقم
خاطئ في حيّز استخدام يشوّه كل مخطط مولَّد، لا حكمًا واحدًا. راجعه أولًا.

قاعدة صيانة: كل حقل رقمي أو منطقي هنا يقابله سجل إثبات في
`codes/uk/provenance_fixtures.py`. الحقول المنطقية مسجّلة أيضًا لأنها
قرارات تخطيطية لا بيانات كتالوج: `needs_drain` يقود فحص أعمدة الصرف،
و`against_wall` يقود الحزم، و`is_worktop` يقود تدقيق المطبخ.

الاصطلاح: `w` العرض على الجدار، `d` البروز منه،
`activity_w × activity_d` حيّز الاستخدام أمام الواجهة.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from planforge.enums import AccessStandard, RoomType


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    code: str
    name_en: str
    name_ar: str
    w: int
    d: int
    activity_w: int
    activity_d: int
    against_wall: bool = True
    needs_drain: bool = False
    is_worktop: bool = False

    @property
    def footprint_mm2(self) -> int:
        return self.w * self.d


def _catalogue() -> dict[str, FixtureSpec]:
    rows: tuple[FixtureSpec, ...] = (
        FixtureSpec("WC", "WC pan", "مرحاض",
                    500, 700, 800, 600, needs_drain=True),
        FixtureSpec("BASIN", "Wash basin", "مغسلة",
                    550, 400, 700, 700, needs_drain=True),
        FixtureSpec("BATH", "Bath 1700", "حوض استحمام",
                    1700, 700, 1100, 700, needs_drain=True),
        FixtureSpec("SHOWER", "Shower 900", "دُش",
                    900, 900, 900, 700, needs_drain=True),
        FixtureSpec("SINK", "Kitchen sink", "حوض مطبخ",
                    600, 600, 1000, 1000,
                    needs_drain=True, is_worktop=True),
        FixtureSpec("HOB", "Hob / cooker", "طبّاخ",
                    600, 600, 1000, 1000, is_worktop=True),
        FixtureSpec("FRIDGE", "Fridge / freezer", "ثلاجة",
                    600, 650, 1000, 1000),
        FixtureSpec("WM", "Washing machine", "غسّالة",
                    600, 600, 900, 900,
                    needs_drain=True, is_worktop=True),
        FixtureSpec("WORKTOP", "Worktop run", "منضدة",
                    1000, 600, 1000, 1000, is_worktop=True),
        FixtureSpec("BED_D", "Double bed", "سرير مزدوج",
                    1500, 2000, 1500, 750),
        FixtureSpec("BED_S", "Single bed", "سرير فردي",
                    900, 1900, 900, 750),
        FixtureSpec("WARDROBE", "Wardrobe", "خزانة",
                    1000, 600, 1000, 750),
        FixtureSpec("DESK", "Desk", "مكتب",
                    1200, 600, 1200, 900),
        FixtureSpec("SOFA", "Sofa 3-seat", "أريكة",
                    2000, 900, 2000, 750),
        FixtureSpec("TABLE4", "Dining table 4", "طاولة طعام 4",
                    1200, 800, 1200, 800, against_wall=False),
        FixtureSpec("TABLE6", "Dining table 6", "طاولة طعام 6",
                    1600, 900, 1600, 900, against_wall=False),
    )
    return {f.code: f for f in rows}


# طقم التجهيزات المطلوب لكل نوع غرفة — وهذا ما يُستنبط منه الحد الأدنى.
# تغييره يغيّر أبعاد المخططات المولَّدة، لا التدقيق وحده.
REQUIRED_SET: dict[RoomType, tuple[str, ...]] = {
    RoomType.WC: ("WC", "BASIN"),
    RoomType.SHOWER_ROOM: ("SHOWER", "WC", "BASIN"),
    RoomType.ENSUITE: ("SHOWER", "WC", "BASIN"),
    RoomType.BATHROOM: ("BATH", "WC", "BASIN"),
    RoomType.UTILITY: ("WM", "SINK"),
    RoomType.KITCHEN: ("SINK", "HOB", "FRIDGE"),
    RoomType.KITCHEN_DINING: ("SINK", "HOB", "FRIDGE", "TABLE4"),
    RoomType.BEDROOM_MAIN: ("BED_D", "WARDROBE"),
    RoomType.BEDROOM_DOUBLE: ("BED_D", "WARDROBE"),
    RoomType.BEDROOM_SINGLE: ("BED_S", "WARDROBE"),
    RoomType.LIVING: ("SOFA",),
    RoomType.DINING: ("TABLE4",),
    RoomType.STUDY: ("DESK",),
    RoomType.MAJLIS: ("SOFA",),
}


@dataclass(frozen=True)
class FixtureProfile:
    edition: str = "2023-01 (غير مُتحقَّق — يلزم توقيع مهندس)"
    verified_by: str = ""
    catalogue: dict[str, FixtureSpec] = field(default_factory=_catalogue)
    required: dict[RoomType, tuple[str, ...]] = field(
        default_factory=lambda: dict(REQUIRED_SET)
    )

    # ─────────── خلوص الدوران ───────────
    turning_space: dict[AccessStandard, int] = field(
        default_factory=lambda: {
            AccessStandard.M4_1: 0,      # صفر = لا يُفرض
            AccessStandard.M4_2: 1200,
            AccessStandard.M4_3: 1500,
        }
    )
    turning_applies: frozenset[RoomType] = frozenset({
        RoomType.WC, RoomType.SHOWER_ROOM, RoomType.BATHROOM,
        RoomType.KITCHEN, RoomType.KITCHEN_DINING, RoomType.BEDROOM_MAIN,
        RoomType.ENTRANCE_HALL,
    })

    # ─────────── المطبخ ───────────
    worktop_run_by_bedspaces: dict[int, int] = field(
        default_factory=lambda: {2: 2500, 4: 3000, 6: 3600, 8: 4200}
    )
    kitchen_gangway: dict[AccessStandard, int] = field(
        default_factory=lambda: {
            AccessStandard.M4_1: 1000,
            AccessStandard.M4_2: 1200,
            AccessStandard.M4_3: 1500,
        }
    )
    worktop_depth: int = 600
    worktop_height: int = 900
    """
    ارتفاع المنضدة. يحدّد أي نافذة تقطع الطول المتاح: نافذة جلستها فوق
    هذا الرقم تمرّ فوق المنضدة ولا تقطعها. تفصيلة تفرّق بين مطبخ يعمل
    ومطبخ يبدو كافيًا على الورق.
    """
    worktop_beside_hob_min: int = 300
    worktop_beside_sink_min: int = 400
    hob_to_sink_min: int = 600
    hob_from_corner_min: int = 300
    hob_under_window_forbidden: bool = True
    corner_loss_mm: int = 600
    """الزاوية غير قابلة للاستخدام على أحد الضلعين المتعامدين."""

    door_swing_clear_of_activity: bool = True

    # ─────────── مشتقات ───────────

    def set_for(self, rtype: RoomType) -> tuple[str, ...]:
        return self.required.get(rtype, ())

    def spec(self, code: str) -> FixtureSpec:
        return self.catalogue[code]

    def needs_drain(self, code: str) -> bool:
        spec = self.catalogue.get(code)
        return bool(spec and spec.needs_drain)

    def worktop_required(self, bedspaces: int) -> int:
        keys = sorted(self.worktop_run_by_bedspaces)
        for k in keys:
            if bedspaces <= k:
                return self.worktop_run_by_bedspaces[k]
        return self.worktop_run_by_bedspaces[keys[-1]]

    def turning_for(
        self, rtype: RoomType, access: AccessStandard
    ) -> int:
        if rtype not in self.turning_applies:
            return 0
        return self.turning_space.get(access, 0)


FIX = FixtureProfile()
