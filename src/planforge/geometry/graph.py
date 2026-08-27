"""
رسم الوصول: من يلامس من، ومن يُمكن الوصول إليه.

التمييز الحاكم: غرفة غير-حركة تُزار ولا يُعبَر منها إلى غيرها. هذا ما يجسّد
مفهوم *inner room* في ADB §2.6 بلا قاعدة منفصلة — والاستثناء المُعلن
هو `access_via` في المتطلب.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from planforge.enums import CIRCULATION, OpeningKind, RoomType
from planforge.model.layout import Layout, RoomInstance, StoreyLayout


@dataclass(frozen=True, slots=True)
class Link:
    a: str
    b: str
    shared_mm: int
    has_opening: bool
    opening_kind: OpeningKind | None


def storey_links(storey: StoreyLayout, min_door_mm: int) -> list[Link]:
    """
    كل زوج غرف متلاصق بطول ≥ خلوص الباب هو رابط ممكن. الفتحة المُعلنة
    في المخطط تجعله رابطًا فعليًا.
    """
    declared: dict[frozenset[str], OpeningKind] = {
        frozenset({o.a, o.b}): o.kind
        for o in storey.openings if o.b is not None
    }
    links: list[Link] = []
    rooms = storey.rooms
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            a, b = rooms[i], rooms[j]
            shared, _ = a.r.shared_edge(b.r)
            if shared < min_door_mm:
                continue
            key = frozenset({a.id, b.id})
            links.append(
                Link(a.id, b.id, shared, key in declared, declared.get(key))
            )
    return links


def access_graph(
    storey: StoreyLayout, min_door_mm: int, declared_only: bool = False
) -> dict[str, set[str]]:
    g: dict[str, set[str]] = {r.id: set() for r in storey.rooms}
    for link in storey_links(storey, min_door_mm):
        if declared_only and not link.has_opening:
            continue
        g[link.a].add(link.b)
        g[link.b].add(link.a)
    return g


def entrance_room(storey: StoreyLayout) -> RoomInstance | None:
    for r in storey.rooms:
        if r.type is RoomType.ENTRANCE_HALL:
            return r
    for r in storey.rooms:
        if r.type in CIRCULATION:
            return r
    return None


def reachable_via_circulation(
    storey: StoreyLayout,
    start_id: str,
    min_door_mm: int,
    extra_transit: frozenset[str] = frozenset(),
) -> set[str]:
    """
    الغرف القابلة للوصول من البداية بالمرور عبر الحركة فقط.

    `extra_transit`: غرف مضيفة مُعلنة بـ`access_via` يُسمح بالعبور عبرها —
    وهي بالضبط ما يفحصه ADB §2.6 كغرف داخلية.
    """
    by_id = {r.id: r for r in storey.rooms}
    g = access_graph(storey, min_door_mm)
    seen = {start_id}
    q = deque([start_id])
    while q:
        cur = q.popleft()
        passable = (
            cur == start_id
            or by_id[cur].type in CIRCULATION
            or cur in extra_transit
        )
        if not passable:
            continue
        for nb in g[cur]:
            if nb not in seen:
                seen.add(nb)
                q.append(nb)
    return seen


def inner_rooms(storey: StoreyLayout, min_door_mm: int) -> dict[str, str]:
    """
    غرفة داخلية = لا تلامس أي حركة، ومنفذها عبر غرفة أخرى.
    يعود {معرّف الغرفة الداخلية: معرّف غرفة الوصول}.
    """
    by_id = {r.id: r for r in storey.rooms}
    g = access_graph(storey, min_door_mm)
    result: dict[str, str] = {}
    for rid, nbs in g.items():
        if by_id[rid].type in CIRCULATION:
            continue
        if not any(by_id[n].type in CIRCULATION for n in nbs) and nbs:
            result[rid] = sorted(nbs)[0]
    return result


def vertical_pairs(layout: Layout) -> list[tuple[RoomInstance, RoomInstance]]:
    """أزواج الغرف المتراكبة رأسيًا بين كل دورين متتاليين."""
    pairs: list[tuple[RoomInstance, RoomInstance]] = []
    ordered = sorted(layout.storeys, key=lambda s: s.index)
    for lower, upper in zip(ordered, ordered[1:]):
        for a in lower.rooms:
            for b in upper.rooms:
                if a.r.overlap_area(b.r) > 0:
                    pairs.append((a, b))
    return pairs
