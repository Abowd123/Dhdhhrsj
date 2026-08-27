"""
تصدير DXF: المخرج القابل للتسليم.

الفرق عن SVG جوهري: هذا مخرج **يُقرأ آليًا** ويُفتح في CAD ويُعدَّل.
فثلاثة أشياء تلزم هنا ولا تلزم هناك:
  • طبقات باصطلاح معروف — المكتب يستلم الملف ويعرف أين كل شيء.
  • أبعاد كيانات DIMENSION حقيقية لا نصوصًا: سحب الجدار في CAD يحدّث
    القياس. النص الثابت يكذب عند أول تعديل.
  • فتحات مقطوعة من الجدران هندسيًا لا محجوبة بصريًا.

القطع بلا عمليات بوليانية: الفتحة محاذية لمحور جدارها بحكم البناء، فنطاق
الجدار يُقسَّم إلى مستطيلات بين الفتحات. دقيقٌ تمامًا، وأبسط من HATCH
بحدود داخلية، ومخرجه يُقرأ آليًا بلا لبس.

⚠ العربية: DXF يحفظ نصًّا واسم خط، وتشكيل الحروف وربطها يجريان في برنامج
العرض. AutoCAD يشكّل؛ عارضات أخرى تُظهر حروفًا منفصلة أو مقلوبة. لا
أستطيع ضمان ما لا أختبره — استخدم `arabic_labels=False` لمخرج مضمون.
"""
from __future__ import annotations
from pathlib import Path
import ezdxf
from ezdxf.document import Drawing as DxfDoc
from ezdxf.layouts import Modelspace
from planforge.drawing.model import (
    ClearRoom, DimChain, Drawing, PlacedFixture, PlacedOpening, StairDraw,
    StoreyDrawing, WALL_LAYER, WallRun,
)
from planforge.enums import Axis, OpeningKind
from planforge.units import area_m2

STOREY_GAP_MM = 4000
"""فراغ بين الأدوار في المساحة النموذجية — الأدوار تُرسم متجاورة أفقيًا."""

LAYERS: dict[str, tuple[int, str]] = {
    "A-WALL": (7, "CONTINUOUS"),
    "A-WALL-PRTY": (7, "CONTINUOUS"),
    "A-WALL-INTR": (8, "CONTINUOUS"),
    "A-WALL-FIRE": (1, "CONTINUOUS"),
    "A-DOOR": (3, "CONTINUOUS"),
    "A-DOOR-FIRE": (1, "CONTINUOUS"),
    "A-GLAZ": (4, "CONTINUOUS"),
    "A-FLOR-STRS": (8, "CONTINUOUS"),
    "A-FURN": (9, "CONTINUOUS"),
    "A-FURN-ACTV": (9, "DASHED"),
    "A-AREA-IDEN": (2, "CONTINUOUS"),
    "A-ANNO-DIMS": (5, "CONTINUOUS"),
    "A-ANNO-TEXT": (7, "CONTINUOUS"),
    "A-ANNO-STMP": (1, "CONTINUOUS"),
}

DIMSTYLE = "PF-MM"
STYLE_AR = "PF-AR"
STYLE_LATIN = "PF-LATIN"
FONT_AR = "arial.ttf"
FONT_LATIN = "isocp.shx"

DOOR_BLOCK = "PF-DOOR"
FIRE_DOOR_BLOCK = "PF-DOOR-FD"
WINDOW_BLOCK = "PF-WIN"


# ═══════════════ التهيئة ═══════════════

def _setup(doc: DxfDoc, arabic: bool) -> None:
    doc.header["$INSUNITS"] = 4          # مليمتر
    doc.header["$MEASUREMENT"] = 1       # متري
    doc.header["$LUNITS"] = 2            # عشري

    for name, (color, linetype) in LAYERS.items():
        if linetype not in doc.linetypes:
            linetype = "CONTINUOUS"
        doc.layers.add(name, color=color, linetype=linetype)

    doc.styles.add(STYLE_LATIN, font=FONT_LATIN)
    if arabic:
        doc.styles.add(STYLE_AR, font=FONT_AR)

    ds = doc.dimstyles.add(DIMSTYLE)
    ds.dxf.dimtxt = 220         # ارتفاع نص البُعد
    ds.dxf.dimasz = 120         # حجم السهم
    ds.dxf.dimexe = 100         # امتداد خط البُعد
    ds.dxf.dimexo = 200         # إزاحة خط الاستدلال
    ds.dxf.dimdec = 0           # مليمترات صحيحة
    ds.dxf.dimlunit = 2
    ds.dxf.dimtxsty = STYLE_LATIN


def _blocks(doc: DxfDoc) -> None:
    """
    بلوكات الفتحات بوحدة قياس 1 مم، تُدرَج بمعامل تحجيم = عرض الفتحة.

    البلوك بوحدة واحدة يعني أن كل الأبواب بلوك واحد: تعديل رسم الباب في
    المكتب يسري على المخطط كله. ولو رُسم كل باب بأبعاده لصار كل باب
    كيانًا مستقلًا لا يُحدَّث.
    """
    for name, layer in (
        (DOOR_BLOCK, "A-DOOR"), (FIRE_DOOR_BLOCK, "A-DOOR-FIRE")
    ):
        blk = doc.blocks.new(name=name)
        blk.add_line((0, 0), (0, 1), dxfattribs={"layer": layer})
        blk.add_arc(
            center=(0, 0), radius=1, start_angle=0, end_angle=90,
            dxfattribs={"layer": layer},
        )

    blk = doc.blocks.new(name=WINDOW_BLOCK)
    for offset in (0.0, 0.5, 1.0):
        blk.add_line(
            (0, offset), (1, offset), dxfattribs={"layer": "A-GLAZ"}
        )


# ═══════════════ الجدران ═══════════════

def _wall_pieces(
    run: WallRun, openings: list[PlacedOpening]
) -> list[tuple[int, int]]:
    """
    مقاطع الجدار الباقية بعد قطع الفتحات، على طوله.

    الفتحات على جدار واحد لا تتراكب بحكم `place_openings`، لكننا ندمج
    المتراكب على أي حال: مقطعٌ سالب الطول يُنتج مضلّعًا مقلوبًا يفسد
    الملف صمتًا.
    """
    cuts = sorted(
        (o.start, o.end) for o in openings
        if o.axis is run.axis and o.coord == run.coord
        and run.contains_span(o.start, o.end)
    )
    pieces: list[tuple[int, int]] = []
    cursor = run.lo
    for lo, hi in cuts:
        if lo > cursor:
            pieces.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < run.hi:
        pieces.append((cursor, run.hi))
    return [(a, b) for a, b in pieces if b > a]


def _draw_walls(
    msp: Modelspace, st: StoreyDrawing, dx: int
) -> None:
    for run in st.runs:
        layer = WALL_LAYER[run.kind]
        t = run.thickness_mm
        half = t // 2
        for lo, hi in _wall_pieces(run, st.openings):
            if run.axis is Axis.V:
                x1, x2 = run.coord - half + dx, run.coord - half + t + dx
                y1, y2 = lo, hi
            else:
                x1, x2 = lo + dx, hi + dx
                y1, y2 = run.coord - half, run.coord - half + t
            msp.add_lwpolyline(
                [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
                close=True,
                dxfattribs={"layer": layer},
            )


# ═══════════════ الفتحات ═══════════════

def _draw_openings(
    msp: Modelspace, st: StoreyDrawing, dx: int
) -> None:
    for o in st.openings:
        ix, iy = o.insert_point()
        w = o.clear_width_mm
        if o.is_door:
            block = (
                FIRE_DOOR_BLOCK if o.kind is OpeningKind.FIRE_DOOR
                else DOOR_BLOCK
            )
            ref = msp.add_blockref(
                block, (ix + dx, iy),
                dxfattribs={
                    "xscale": w, "yscale": w, "zscale": 1,
                    "rotation": o.rotation_deg(),
                    "layer": (
                        "A-DOOR-FIRE"
                        if o.kind is OpeningKind.FIRE_DOOR else "A-DOOR"
                    ),
                },
            )
            if o.fire_rating:
                # التصنيف يُكتب نصًّا مجاورًا: جدول الأبواب في المكتب
                # يُبنى من هذه النصوص، وحملُه في اسم البلوك يمنع تجميعها
                msp.add_text(
                    o.fire_rating,
                    height=140,
                    dxfattribs={
                        "layer": "A-ANNO-TEXT", "style": STYLE_LATIN,
                    },
                ).set_placement((ix + dx, iy))
            del ref
            continue

        # النافذة: بلوك ممدود على طول الفتحة وبسماكة الجدار
        t = o.thickness_mm
        rotation = 0.0 if o.axis is Axis.H else 90.0
        if o.axis is Axis.H:
            base = (o.start + dx, o.coord - t // 2)
        else:
            base = (o.coord + t // 2 + dx, o.start)
        msp.add_blockref(
            WINDOW_BLOCK, base,
            dxfattribs={
                "xscale": w, "yscale": t, "zscale": 1,
                "rotation": rotation, "layer": "A-GLAZ",
            },
        )


# ═══════════════ السلّم والتجهيزات ═══════════════

def _draw_stair(msp: Modelspace, stair: StairDraw, dx: int) -> None:
    x, y, w, h = stair.rect
    msp.add_lwpolyline(
        [
            (x + dx, y), (x + w + dx, y),
            (x + w + dx, y + h), (x + dx, y + h),
        ],
        close=True, dxfattribs={"layer": "A-FLOR-STRS"},
    )
    for r in stair.risers:
        if stair.horizontal:
            msp.add_line(
                (r + dx, y), (r + dx, y + h),
                dxfattribs={"layer": "A-FLOR-STRS"},
            )
        else:
            msp.add_line(
                (x + dx, r), (x + w + dx, r),
                dxfattribs={"layer": "A-FLOR-STRS"},
            )
    if stair.n_risers:
        msp.add_text(
            f"{stair.n_risers}R @ {stair.rise_mm:.0f} / "
            f"{stair.going_mm}G  UP",
            height=180,
            dxfattribs={"layer": "A-ANNO-TEXT", "style": STYLE_LATIN},
        ).set_placement((x + dx + 150, y + h + 250))


def _draw_fixtures(
    msp: Modelspace, fixtures: list[PlacedFixture], dx: int
) -> None:
    for f in fixtures:
        ax, ay, aw, ah = f.activity
        msp.add_lwpolyline(
            [
                (ax + dx, ay), (ax + aw + dx, ay),
                (ax + aw + dx, ay + ah), (ax + dx, ay + ah),
            ],
            close=True, dxfattribs={"layer": "A-FURN-ACTV"},
        )
        msp.add_lwpolyline(
            [
                (f.x + dx, f.y), (f.x + f.w + dx, f.y),
                (f.x + f.w + dx, f.y + f.h), (f.x + dx, f.y + f.h),
            ],
            close=True, dxfattribs={"layer": "A-FURN"},
        )
        msp.add_text(
            f.code, height=120,
            dxfattribs={"layer": "A-FURN", "style": STYLE_LATIN},
        ).set_placement(
            (f.x + dx + 60, f.y + 60)
        )


# ═══════════════ الأبعاد والمسميات ═══════════════

def _draw_dims(msp: Modelspace, chains: list[DimChain], dx: int) -> None:
    """
    كيانات DIMENSION حقيقية.

    `render()` ضرورية: بلا استدعائها لا تُرسم الأبعاد في العارضات التي لا
    تحسب الكيانات التابعة بنفسها، فيُفتح الملف وكأنه بلا أبعاد.
    """
    for chain in chains:
        for a, b in zip(chain.ticks, chain.ticks[1:]):
            if b - a <= 0:
                continue
            if chain.axis is Axis.H:
                p1 = (a + dx, chain.base)
                p2 = (b + dx, chain.base)
                angle = 0.0
            else:
                p1 = (chain.base + dx, a)
                p2 = (chain.base + dx, b)
                angle = 90.0
            dim = msp.add_linear_dim(
                base=p1, p1=p1, p2=p2, angle=angle,
                dimstyle=DIMSTYLE,
                dxfattribs={"layer": "A-ANNO-DIMS"},
            )
            dim.render()


def _draw_labels(
    msp: Modelspace, st: StoreyDrawing, dx: int, arabic: bool
) -> None:
    for lb in st.labels:
        px, py = lb.point
        style = STYLE_AR if (lb.arabic and arabic) else STYLE_LATIN
        text = lb.text
        if lb.arabic and not arabic:
            continue        # العربية مُعطَّلة: السطر اللاتيني يكفي
        mt = msp.add_mtext(
            text,
            dxfattribs={
                "layer": lb.layer, "style": style,
                "char_height": lb.height_mm,
                "attachment_point": 5,      # وسط-وسط
            },
        )
        mt.set_location((px + dx, py))


def _draw_room_boundaries(
    msp: Modelspace, rooms: list[ClearRoom], dx: int
) -> None:
    """
    مضلّعات الغرف الصافية على طبقة المساحات.

    غرضها أن يقيس المكتب المساحة من الملف لا من نصّ فيه: مضلّع مغلق
    على `A-AREA-IDEN` يقرؤه CAD ويحسب مساحته، فيُصدَّق الرقم المكتوب.
    """
    for r in rooms:
        msp.add_lwpolyline(
            [
                (r.x + dx, r.y), (r.x2 + dx, r.y),
                (r.x2 + dx, r.y2), (r.x + dx, r.y2),
            ],
            close=True, dxfattribs={"layer": "A-AREA-IDEN"},
        )


def _draw_stamp(
    msp: Modelspace, dwg: Drawing, stamp: str, note: str, dx_end: int
) -> None:
    """
    الختم في المخرج نفسه.

    المخرج يُنسخ ويُطبَع ويُرسل بلا تقريره، فحالة الاعتماد ترافقه أو
    تُفقد. اللاتينية مقصودة: الختم يجب أن يُقرأ في أي عارض.
    """
    lines = [
        stamp,
        f"PROJECT: {dwg.project_name}",
        f"ENGINE: {dwg.engine_version}",
        f"SCALE: 1:{dwg.scale_denominator} @ A1",
        f"CLEAR GIA: {area_m2(dwg.total_gia_mm2):.2f} m2",
    ]
    if note:
        lines.append(note)
    y = -6000
    for line in lines:
        msp.add_text(
            line, height=300,
            dxfattribs={"layer": "A-ANNO-STMP", "style": STYLE_LATIN},
        ).set_placement((0, y))
        y -= 450


# ═══════════════ المدخل ═══════════════

def export_dxf(
    dwg: Drawing,
    path: Path,
    *,
    stamp: str,
    arabic_labels: bool = True,
    include_fixtures: bool = True,
    include_dims: bool = True,
) -> tuple[Path, dict[str, int]]:
    """
    يكتب DXF R2013 ويُعيد (المسار، إحصاء ما رُسم).

    `arabic_labels=False` مخرج مضمون في كل العارضات: مسميات الغرف
    اللاتينية والأبعاد الرقمية وحدها. الافتراض `True` يكتب العربية
    ويعتمد على تشكيل البرنامج المستقبِل.
    """
    doc = ezdxf.new("R2013", setup=True)
    _setup(doc, arabic_labels)
    _blocks(doc)
    msp = doc.modelspace()

    counts = {"storeys": 0, "walls": 0, "openings": 0, "fixtures": 0}
    dx = 0
    for st in sorted(dwg.storeys, key=lambda s: s.index):
        _draw_room_boundaries(msp, st.rooms, dx)
        _draw_walls(msp, st, dx)
        _draw_openings(msp, st, dx)
        if st.stair is not None:
            _draw_stair(msp, st.stair, dx)
        if include_fixtures:
            _draw_fixtures(msp, st.fixtures, dx)
            counts["fixtures"] += len(st.fixtures)
        if include_dims:
            _draw_dims(msp, st.dims, dx)
        _draw_labels(msp, st, dx, arabic_labels)

        msp.add_text(
            f"STOREY {st.index}", height=500,
            dxfattribs={"layer": "A-ANNO-TEXT", "style": STYLE_LATIN},
        ).set_placement((dx + 200, st.envelope[1] + st.envelope[3] + 1200))

        counts["storeys"] += 1
        counts["walls"] += len(st.runs)
        counts["openings"] += len(st.openings)
        dx += st.envelope[2] + STOREY_GAP_MM

    note = (
        "" if arabic_labels
        else "ARABIC LABELS DISABLED - LATIN ONLY"
    )
    _draw_stamp(msp, dwg, stamp, note, dx)

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    return path, counts
