"""
حزمة قواعد اختيارية للنمط الخليجي.

تُشغَّل فقط عند `brief.majlis_mode != NONE`. مراجع مخالفاتها «متطلب
ثقافي» لا فقرة قانونية — فلا تُنسب سلطةٌ إلى ما لا نصّ له، وهذا هو
سبب فصلها عن `codes/uk/`.

الرقم الوحيد الذي تقرؤه من ملف الكود هو خلوص الباب، وتقرؤه لبناء رسم
الوصول لا كمتطلب ثقافي.
"""
from __future__ import annotations
from typing import Iterable
from planforge.codes.uk.profile import UK
from planforge.enums import BEDROOMS, MajlisMode, OpeningKind, RoomType
from planforge.geometry.graph import access_graph
from planforge.model.brief import Brief
from planforge.model.layout import Layout
from planforge.rules.core import Rule, Severity, Violation

CULTURAL = "متطلب ثقافي (لا نص قانوني)"
PRIVACY = "متطلب ثقافي — خصوصية"

FAMILY_TYPES = frozenset({
    RoomType.LIVING, RoomType.DINING, RoomType.KITCHEN,
    RoomType.KITCHEN_DINING,
}) | BEDROOMS

GUEST_WC = frozenset({RoomType.WC, RoomType.SHOWER_ROOM})
DOOR_KINDS = frozenset({OpeningKind.DOOR, OpeningKind.FIRE_DOOR})


def r_majlis(layout: Layout, brief: Brief) -> Iterable[Violation]:
    mode = brief.majlis_mode
    if mode is MajlisMode.NONE:
        return

    majlis = [r for r in layout.all_rooms() if r.type is RoomType.MAJLIS]
    if not majlis:
        yield Violation(
            "CUL-MAJ-001", Severity.ERROR,
            "نمط المجلس مُفعَّل ولا مجلس في المخطط",
            CULTURAL, None, (), "0", "≥ 1",
        )
        return

    entrance = brief.entrance_storey
    door = UK.door_min_clear_width[brief.access_standard]

    for mj in majlis:
        if mj.storey != entrance:
            yield Violation(
                "CUL-MAJ-002", Severity.ERROR,
                "المجلس يجب أن يكون في دور الدخول",
                CULTURAL, mj.storey, (mj.id,),
                f"دور {mj.storey}", f"دور {entrance}",
            )
            continue

        s = layout.storey(mj.storey)
        by_id = {r.id: r for r in s.rooms}
        nbs = access_graph(s, door).get(mj.id, set())

        if not any(
            by_id[n].type is RoomType.ENTRANCE_HALL for n in nbs
        ):
            yield Violation(
                "CUL-MAJ-003", Severity.ERROR,
                "المجلس غير متصل بردهة الدخول مباشرة",
                CULTURAL, mj.storey, (mj.id,),
                "بلا تلاصق", "تلاصق مع ردهة الدخول",
            )

        if mode in {MajlisMode.GUEST_WING, MajlisMode.SEPARATE_ENTRANCE}:
            if not any(by_id[n].type in GUEST_WC for n in nbs):
                yield Violation(
                    "CUL-MAJ-004", Severity.ERROR,
                    "جناح الضيوف يحتاج دورة مياه ملاصقة للمجلس",
                    CULTURAL, mj.storey, (mj.id,),
                    "بلا دورة مياه ملاصقة", "دورة مياه ملاصقة",
                )
            for n in sorted(n for n in nbs if by_id[n].type in FAMILY_TYPES):
                yield Violation(
                    "CUL-MAJ-005", Severity.ERROR,
                    "اتصال مباشر بين المجلس والمنطقة العائلية",
                    PRIVACY, mj.storey, (mj.id, n),
                    str(by_id[n].type), "فصل بردهة أو حائط",
                )

        if mode is MajlisMode.SEPARATE_ENTRANCE:
            env = s.envelope.to_rect()
            edges = mj.r.external_edges(env)
            if brief.street_side not in edges:
                yield Violation(
                    "CUL-MAJ-006", Severity.ERROR,
                    "المجلس بمدخل مستقل يجب أن يلامس واجهة الشارع",
                    CULTURAL, mj.storey, (mj.id,),
                    ", ".join(sorted(str(e) for e in edges)) or "بلا واجهة",
                    str(brief.street_side),
                )
            has_door = any(
                o.a == mj.id and o.is_external and o.kind in DOOR_KINDS
                for o in s.openings
            )
            if not has_door:
                yield Violation(
                    "CUL-MAJ-007", Severity.ERROR,
                    "لا باب خارجي مستقل للمجلس",
                    CULTURAL, mj.storey, (mj.id,), "0", "≥ 1",
                )


MAJLIS_RULES: list[Rule] = [
    Rule("CUL-MAJLIS", "نمط المجلس وجناح الضيوف", CULTURAL,
         r_majlis, frozenset({"culture"}),
         ("CUL-MAJ-001", "CUL-MAJ-002", "CUL-MAJ-003", "CUL-MAJ-004",
          "CUL-MAJ-005", "CUL-MAJ-006", "CUL-MAJ-007")),
]
