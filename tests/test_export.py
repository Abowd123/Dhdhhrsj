"""التصدير يُنتج ملفًا يُقرأ، ويحمل الختم."""
from __future__ import annotations
import pytest


def test_svg_contains_walls_and_stamp(solved):
    from planforge.export.svg import drawing_svg

    html = drawing_svg(
        solved.drawing,
        unfurnishable=frozenset(),
        stamp="NOT FOR CONSTRUCTION — test",
    )
    assert "<svg" in html
    assert "data-wall=" in html
    assert "NOT FOR CONSTRUCTION" in html


def test_svg_marks_unfurnishable_rooms(solved):
    from planforge.export.svg import ROOM_FAIL_FILL, storey_svg

    st = solved.drawing.storeys[0]
    rid = st.rooms[0].id
    out = storey_svg(st, unfurnishable=frozenset({rid}))
    assert ROOM_FAIL_FILL in out


def test_dxf_writes_and_reopens(solved, tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    from planforge.export.dxf import LAYERS, export_dxf

    path, counts = export_dxf(
        solved.drawing, tmp_path / "plan.dxf",
        stamp="NOT FOR CONSTRUCTION — test",
        arabic_labels=False,
    )
    assert path.exists()
    assert counts["walls"] > 0
    assert counts["openings"] > 0

    doc = ezdxf.readfile(path)
    names = {layer.dxf.name for layer in doc.layers}
    for expected in ("A-WALL", "A-DOOR", "A-ANNO-DIMS", "A-ANNO-STMP"):
        assert expected in names
    assert set(LAYERS) <= names

    msp = doc.modelspace()
    assert len(msp.query("LWPOLYLINE")) > 0
    assert len(msp.query("INSERT")) > 0, "لا بلوكات فتحات"
    texts = " ".join(
        e.dxf.text for e in msp.query("TEXT")
    )
    assert "NOT FOR CONSTRUCTION" in texts


def test_dxf_cuts_openings_out_of_walls(solved, tmp_path):
    """
    الفتحة تقطع الجدار فعلًا: مسار الجدار الحامل لفتحة يُنتج مقطعين على
    الأقل، أو مقطعًا واحدًا إن كانت الفتحة عند طرفه.
    """
    pytest.importorskip("ezdxf")
    from planforge.export.dxf import _wall_pieces

    for st in solved.drawing.storeys:
        for o in st.openings:
            run = st.run_carrying(o)
            if run is None:
                continue
            pieces = _wall_pieces(run, st.openings)
            covered = sum(b - a for a, b in pieces)
            assert covered < run.length, (
                f"{run.id}: الفتحة {o.id} لم تُقطع"
            )
            assert all(b > a for a, b in pieces), "مقطع سالب الطول"
            break


def test_svg_labels_land_inside_the_view(solved):
    """
    الانحدار المحروس: الهندسة كانت تُرسم في مجموعة مقلوبة والنصوص في
    مجموعة غير مقلوبة، فيقع كل مسمّى غرفة خارج الرسم كليًّا.
    """
    import re
    from planforge.export.svg import MARGIN_MM, storey_svg

    st = solved.drawing.storeys[0]
    _x, y, _w, h = st.envelope
    vy, vh = y - MARGIN_MM, h + 2 * MARGIN_MM
    out = storey_svg(st, show_fixtures=False, show_dims=False)

    ys = [int(v) for v in re.findall(r'<text x="-?\d+" y="(-?\d+)"', out)]
    assert ys, "لا مسميات في المخرج"
    for value in ys:
        assert vy <= value <= vy + vh, (
            f"مسمّى عند y={value} خارج نطاق العرض [{vy}, {vy + vh}]"
        )


def test_dxf_arabic_flag_is_honest(solved, tmp_path):
    """
    تعطيل العربية يُعلن نفسه في المخرج.

    مخرجٌ ناقص المسميات بلا إعلان يُقرأ مخرجًا كاملًا.
    """
    ezdxf = pytest.importorskip("ezdxf")
    from planforge.export.dxf import export_dxf

    path, _ = export_dxf(
        solved.drawing, tmp_path / "latin.dxf",
        stamp="test", arabic_labels=False,
    )
    doc = ezdxf.readfile(path)
    texts = " ".join(e.dxf.text for e in doc.modelspace().query("TEXT"))
    assert "ARABIC LABELS DISABLED" in texts
