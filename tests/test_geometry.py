"""تبليط تام، وطوبولوجيا قابلة للعكس."""
from __future__ import annotations
import pytest
from planforge.enums import Axis
from planforge.geometry.lines import (
    build_topology, current_coords, rects_from_lines,
)
from planforge.geometry.rect import Rect
from planforge.geometry.tiling import boundary_segments, segments_on_axis

ENV = Rect(0, 0, 6000, 4000)
TILING = {
    "a": Rect(0, 0, 3000, 4000),
    "b": Rect(3000, 0, 3000, 2000),
    "c": Rect(3000, 2000, 3000, 2000),
}


def test_tiling_is_complete_and_disjoint():
    assert sum(r.area for r in TILING.values()) == ENV.area
    items = list(TILING.values())
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            dx = min(a.x2, b.x2) - max(a.x, b.x)
            dy = min(a.y2, b.y2) - max(a.y, b.y)
            assert dx <= 0 or dy <= 0, "تراكب"


def test_every_segment_knows_its_sides():
    segs = boundary_segments(TILING, ENV)
    assert segs
    for s in segs:
        assert s.length > 0
        assert not (s.a is None and s.b is None), (
            "مقطع لا يفصل شيئًا عن شيء"
        )


def test_internal_segment_between_expected_rooms():
    segs = segments_on_axis(TILING, ENV, Axis.V)
    internal = [s for s in segs if not s.is_external]
    assert any(
        s.room_set() == frozenset({"a", "b"}) for s in internal
    )
    assert any(
        s.room_set() == frozenset({"a", "c"}) for s in internal
    )


def test_external_segments_cover_perimeter():
    """
    مجموع أطوال المقاطع الخارجية = محيط المظروف.

    شرطٌ لازم لصحة النوافذ: واجهةٌ مفقودة تعني غرفة تُحكَم بأنها بلا
    واجهة خارجية وهي عليها.
    """
    segs = boundary_segments(TILING, ENV)
    total = sum(s.length for s in segs if s.is_external)
    assert total == 2 * (ENV.w + ENV.h)


def test_topology_roundtrip():
    topo = build_topology(0, ENV, TILING)
    rebuilt = rects_from_lines(topo, current_coords(topo))
    assert rebuilt == TILING


def test_every_room_has_four_lines():
    topo = build_topology(0, ENV, TILING)
    for rid in TILING:
        lines = topo.lines_of_room(rid)
        assert len(lines) == 4
        assert len({l.id for l in lines}) == 4


def test_boundary_lines_are_immovable():
    topo = build_topology(0, ENV, TILING)
    boundary = [l for l in topo.lines.values() if l.is_boundary]
    assert len(boundary) == 4, "حدود المظروف الأربعة"
    assert all(not l.movable for l in boundary)
    assert topo.movable_lines(), "لا خط قابل للتحريك — المحرر عاطل"


def test_irregular_tiling_is_rejected():
    """
    تبليط غير منتظم يرفع خطأً لا يُنتج طوبولوجيا ناقصة.

    الفشل الصريح هنا أرخص من مخطط يبدو صحيحًا وتُفقد فيه غرفة عند أول
    سحبة جدار.
    """
    bad = {"a": Rect(0, 0, 1000, 1000), "b": Rect(2500, 2500, 500, 500)}
    with pytest.raises(ValueError, match="غير منتظم"):
        build_topology(0, ENV, bad)


def test_neighbours_bracket_a_line():
    topo = build_topology(0, ENV, TILING)
    inner = [
        l for l in topo.of_axis(Axis.V) if not l.is_boundary
    ]
    if not inner:
        pytest.skip("لا خط داخلي رأسي في هذا التبليط")
    before, after = topo.neighbours(inner[0].id)
    assert before is not None or after is not None
