from __future__ import annotations
from enum import StrEnum


class RoomType(StrEnum):
    # حركة
    ENTRANCE_HALL = "entrance_hall"
    HALL = "hall"
    LANDING = "landing"
    STAIR = "stair"
    LOBBY = "lobby"           # ردهة فاصلة (تلزم لفصل WC عن المطبخ)
    # قابلة للسكن
    LIVING = "living"
    DINING = "dining"
    KITCHEN = "kitchen"
    KITCHEN_DINING = "kitchen_dining"
    STUDY = "study"
    BEDROOM_MAIN = "bedroom_main"
    BEDROOM_DOUBLE = "bedroom_double"
    BEDROOM_SINGLE = "bedroom_single"
    MAJLIS = "majlis"
    # رطبة
    BATHROOM = "bathroom"
    SHOWER_ROOM = "shower_room"
    ENSUITE = "ensuite"
    WC = "wc"
    UTILITY = "utility"
    # خدمة
    STORAGE = "storage"
    PLANT = "plant"
    GARAGE = "garage"


CIRCULATION = frozenset({
    RoomType.ENTRANCE_HALL, RoomType.HALL, RoomType.LANDING,
    RoomType.STAIR, RoomType.LOBBY,
})

# "Habitable room" بمفهوم ADB/ADF: غرفة للسكن أو النوم. لا تشمل المطبخ
# الصِرف ولا الحمامات ولا الحركة.
HABITABLE = frozenset({
    RoomType.LIVING, RoomType.DINING, RoomType.KITCHEN_DINING,
    RoomType.STUDY, RoomType.BEDROOM_MAIN, RoomType.BEDROOM_DOUBLE,
    RoomType.BEDROOM_SINGLE, RoomType.MAJLIS,
})

BEDROOMS = frozenset({
    RoomType.BEDROOM_MAIN, RoomType.BEDROOM_DOUBLE, RoomType.BEDROOM_SINGLE,
})

WET = frozenset({
    RoomType.BATHROOM, RoomType.SHOWER_ROOM, RoomType.ENSUITE,
    RoomType.WC, RoomType.UTILITY, RoomType.KITCHEN,
    RoomType.KITCHEN_DINING,
})

# غرف تحتاج نافذة إلى الهواء الخارجي (ADF: تهوية تنظيف)
NEEDS_PURGE_VENT = HABITABLE | {RoomType.KITCHEN, RoomType.UTILITY}

# غرف تحتاج شفطًا ميكانيكيًا (ADF جدول 1.1)
NEEDS_EXTRACT = frozenset({
    RoomType.KITCHEN, RoomType.KITCHEN_DINING, RoomType.UTILITY,
    RoomType.BATHROOM, RoomType.SHOWER_ROOM, RoomType.ENSUITE, RoomType.WC,
})

# ADB Vol 1: الأنواع المسموح أن تكون "غرفة داخلية" (inner room)
INNER_ROOM_ALLOWED = frozenset({
    RoomType.KITCHEN, RoomType.UTILITY, RoomType.BATHROOM,
    RoomType.SHOWER_ROOM, RoomType.ENSUITE, RoomType.WC,
    RoomType.STORAGE, RoomType.LOBBY, RoomType.PLANT,
})


class Side(StrEnum):
    NORTH = "north"
    EAST = "east"
    SOUTH = "south"
    WEST = "west"


class AccessStandard(StrEnum):
    """Approved Document M (2015) Vol 1 — فئات المساكن."""
    M4_1 = "M4(1)"   # visitable
    M4_2 = "M4(2)"   # accessible and adaptable
    M4_3 = "M4(3)"   # wheelchair user


class MajlisMode(StrEnum):
    NONE = "none"
    INTEGRATED = "integrated"                # مجلس متصل بردهة الدخول
    GUEST_WING = "guest_wing"                # مجلس + دورة مياه ضيوف معزولان
    SEPARATE_ENTRANCE = "separate_entrance"  # + مدخل مستقل من الشارع


class RelationKind(StrEnum):
    ADJACENT = "adjacent"            # يجب التلاصق
    DIRECT_ACCESS = "direct_access"  # يجب باب مباشر
    NOT_ADJACENT = "not_adjacent"    # يُمنع التلاصق
    SAME_STOREY = "same_storey"
    STACKED = "stacked"              # فوق بعضهما رأسيًا


class OpeningKind(StrEnum):
    DOOR = "door"
    FIRE_DOOR = "fire_door"   # FD30
    WINDOW = "window"
    ESCAPE_WINDOW = "escape_window"
    OPEN = "open"             # فتحة بلا باب (مخطط مفتوح)


class Axis(StrEnum):
    """محور خط: V = إحداثي ثابت على x، H = ثابت على y."""
    V = "vertical"
    H = "horizontal"

    @property
    def other(self) -> "Axis":
        return Axis.H if self is Axis.V else Axis.V
