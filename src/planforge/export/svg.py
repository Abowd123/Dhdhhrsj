"""
تصدير SVG: للعرض في المحرر لا للتسليم.

الفرق عن DXF جوهري: هذا مخرج **بصري** — لا طبقات CAD ولا أبعاد قابلة
للتحديث ولا بلوكات. غرضه أن يرى المهندس ما يعدّله فورًا، وأن تُقرأ
الحالة بالعين: الغرفة غير القابلة للتأثيث مظلّلة، والفتحة التي لم تُحلّ
غائبة عن الرسم — وغيابها نفسه معلومة.

نظام الإحداثيات مقلوب: النموذج y إلى أعلى، وSVG y إلى أسفل. القلب يجري
بتحويل واحد على المجموعة الجذرية لا بحساب في كل عنصر.
"""
from __future__ import annotations
from xml.sax.saxutils import escape
from planforge.drawing.model import (
    Drawing, PlacedFixture, PlacedOpening, StairDraw, StoreyDrawing,
    WallKind, WallRun,
)
from planforge.enums import Axis, OpeningKind
from planforge.units import area_m2

MARGIN_MM = 3500
WALL_FILL = {
    WallKind.EXTERNAL: "#2b2b2b",
    WallKind.PARTY: "#000000",
    WallKind.LOADBEARING: "#3d3d3d",
    WallKind.PARTITION: "#7a7a7a",
    WallKind.FIRE: "#8a2f2f",
}
ROOM_FILL = "#fbfbf8"
ROOM_FAIL_FILL = "#fdecec"
FIXTURE_FILL = "#dfe6ee"
ACTIVITY_FILL = "#eef3f8"
STAIR_STROKE = "#4a4a4a"
DIM_STROKE = "#9aa5b1"


def _esc(text: str) -> str:
    return escape(str(text))


def _wall_rect(run: WallRun) -> tuple[int, int, int, int]:
    return run.band()


def _opening_gap(o: PlacedOpening) -> tuple[int, int, int, int]:
    """
    مستطيل يمحو الجدار موضع الفتحة.

    نرسمه بلون الخلفية بدل طرح هندسي: الطرح في SVG يحتاج `mask` لكل
    جدار، والنتيجة البصرية واحدة. لا يصلح هذا في DXF — هناك الطرح
    ضروري لأن المخرج يُقرأ آليًا.
    """
    t = o.thickness_mm
    if o.axis is Axis.V:
        return (o.coord - t // 2 - 1, o.start, t + 2, o.clear_width_mm)
    return (o.start, o.coord - t // 2 - 1, o.clear_width_mm, t + 2)


def _swing_path(o: PlacedOpening) -> str:
    """قوس دوران الباب: من المفصلة إلى نهاية الفتحة."""
    w = o.clear_width_mm
    hx, hy = o.insert_point()
    sign = 1 if o.swing_positive else -1
    if o.axis is Axis.V:
        ex, ey = hx + sign * w, hy
        lx, ly = hx, hy + (w if o.hinge_left else -w)
    else:
        ex, ey = hx, hy + sign * w
        lx, ly = hx + (w if o.hinge_left else -w), hy
    return (
        f"M {lx} {ly} L {hx} {hy} "
        f"M {hx} {hy} A {w} {w} 0 0 1 {ex} {ey}"
    )


def _fixture(f: PlacedFixture) -> str:
    ax, ay, aw, ah = f.activity
    return (
        f'<rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" '
        f'fill="{ACTIVITY_FILL}" stroke="#c8d4e0" stroke-width="12" '
        f'stroke-dasharray="90 70"/>'
        f'<rect x="{f.x}" y="{f.y}" width="{f.w}" height="{f.h}" '
        f'fill="{FIXTURE_FILL}" stroke="#8fa3b8" stroke-width="18"/>'
    )


def _stair(st: StairDraw) -> str:
    x, y, w, h = st.rect
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
        f'fill="none" stroke="{STAIR_STROKE}" stroke-width="18"/>'
    ]
    for r in st.risers:
        if st.horizontal:
            parts.append(
                f'<line x1="{r}" y1="{y}" x2="{r}" y2="{y + h}" '
                f'stroke="{STAIR_STROKE}" stroke-width="14"/>'
            )
        else:
            parts.append(
                f'<line x1="{x}" y1="{r}" x2="{x + w}" y2="{r}" '
                f'stroke="{STAIR_STROKE}" stroke-width="14"/>'
            )
    # سهم اتجاه الصعود
    if st.horizontal:
        parts.append(
            f'<line x1="{x + 200}" y1="{y + h // 2}" '
            f'x2="{x + w - 200}" y2="{y + h // 2}" '
            f'stroke="{STAIR_STROKE}" stroke-width="22" '
            f'marker-end="url(#up)"/>'
        )
    else:
        parts.append(
            f'<line x1="{x + w // 2}" y1="{y + 200}" '
            f'x2="{x + w // 2}" y2="{y + h - 200}" '
            f'stroke="{STAIR_STROKE}" stroke-width="22" '
            f'marker-end="url(#up)"/>'
        )
    return "".join(parts)


def _dims(st: StoreyDrawing) -> str:
    parts: list[str] = []
    for chain in st.dims:
        for a, b in zip(chain.ticks, chain.ticks[1:]):
            if chain.axis is Axis.H:
                parts.append(
                    f'<line x1="{a}" y1="{chain.base}" x2="{b}" '
                    f'y2="{chain.base}" stroke="{DIM_STROKE}" '
                    f'stroke-width="14"/>'
                    f'<text x="{(a + b) // 2}" y="{chain.base - 90}" '
                    f'class="dim" transform="scale(1,-1) '
                    f'translate(0,{-2 * (chain.base - 90)})">'
                    f'{b - a}</text>'
                )
            else:
                parts.append(
                    f'<line x1="{chain.base}" y1="{a}" '
                    f'x2="{chain.base}" y2="{b}" stroke="{DIM_STROKE}" '
                    f'stroke-width="14"/>'
                )
    return "".join(parts)


def storey_svg(
    st: StoreyDrawing,
    *,
    unfurnishable: frozenset[str] = frozenset(),
    show_fixtures: bool = True,
    show_dims: bool = True,
) -> str:
    """SVG لدور واحد. يُعاد `<svg>` مستقلًّا صالحًا للحقن مباشرة."""
    x, y, w, h = st.envelope
    vx = x - MARGIN_MM
    vy = y - MARGIN_MM
    vw = w + 2 * MARGIN_MM
    vh = h + 2 * MARGIN_MM

    body: list[str] = []

    for r in st.rooms:
        fill = ROOM_FAIL_FILL if r.id in unfurnishable else ROOM_FILL
        body.append(
            f'<rect x="{r.x}" y="{r.y}" width="{r.w}" height="{r.h}" '
            f'fill="{fill}" data-room="{_esc(r.id)}" class="room"/>'
        )

    if show_fixtures:
        body.extend(_fixture(f) for f in st.fixtures)

    if st.stair is not None:
        body.append(_stair(st.stair))

    for run in st.runs:
        rx, ry, rw, rh = _wall_rect(run)
        body.append(
            f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" '
            f'fill="{WALL_FILL[run.kind]}" data-wall="{_esc(run.id)}" '
            f'class="wall"/>'
        )

    for o in st.openings:
        gx, gy, gw, gh = _opening_gap(o)
        body.append(
            f'<rect x="{gx}" y="{gy}" width="{gw}" height="{gh}" '
            f'fill="#ffffff" data-opening="{_esc(o.id)}"/>'
        )
        if o.is_door:
            stroke = (
                "#8a2f2f" if o.kind is OpeningKind.FIRE_DOOR else "#5a6b7c"
            )
            body.append(
                f'<path d="{_swing_path(o)}" fill="none" stroke="{stroke}" '
                f'stroke-width="16" data-swing="{_esc(o.id)}"/>'
            )
        else:
            if o.axis is Axis.V:
                body.append(
                    f'<line x1="{o.coord}" y1="{o.start}" x2="{o.coord}" '
                    f'y2="{o.end}" stroke="#4a7fa8" stroke-width="26"/>'
                )
            else:
                body.append(
                    f'<line x1="{o.start}" y1="{o.coord}" x2="{o.end}" '
                    f'y2="{o.coord}" stroke="#4a7fa8" stroke-width="26"/>'
                )

    if show_dims:
        body.append(_dims(st))

    # النصوص خارج المجموعة المقلوبة كي تُقرأ في اتجاهها الصحيح، فيلزم
    # إسقاط y بالتحويل نفسه يدويًا: y' = 2·vy + vh − y.
    texts: list[str] = []
    for lb in st.labels:
        px, py = lb.point
        rtl = ' direction="rtl"' if lb.arabic else ""
        texts.append(
            f'<text x="{px}" y="{2 * vy + vh - py}" '
            f'font-size="{lb.height_mm}" text-anchor="middle" '
            f'class="lbl"{rtl}>{_esc(lb.text)}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vx} {vy} {vw} {vh}" '
        f'data-storey="{st.index}" class="plan">'
        f'<defs><marker id="up" markerWidth="6" markerHeight="6" '
        f'refX="5" refY="3" orient="auto">'
        f'<path d="M0,0 L6,3 L0,6 z" fill="{STAIR_STROKE}"/>'
        f'</marker></defs>'
        f'<style>.lbl{{font-family:sans-serif;fill:#333}}'
        f'.dim{{font-family:sans-serif;font-size:220px;fill:#667}}'
        f'.room{{stroke:none}}</style>'
        f'<g transform="scale(1,-1) translate(0,{-2 * vy - vh})">'
        f'{"".join(body)}</g>'
        f'<g>{"".join(texts)}</g>'
        f'</svg>'
    )


def drawing_svg(
    dwg: Drawing,
    *,
    unfurnishable: frozenset[str] = frozenset(),
    stamp: str = "",
    **kw,
) -> str:
    """
    كل الأدوار في وثيقة واحدة، مع الختم.

    الختم يُكتب في المخرج نفسه لا في تقرير منفصل: مخرجٌ يُنسخ ويُرسل
    ويُطبع بلا تقريره، فالحالة تُرافقه أو تُفقد.
    """
    parts = [
        f'<section data-storey="{st.index}">'
        f'<h3>دور {st.index} — '
        f'{area_m2(st.gia_mm2):.2f} م² صافٍ</h3>'
        f'{storey_svg(st, unfurnishable=unfurnishable, **kw)}'
        f'</section>'
        for st in sorted(dwg.storeys, key=lambda s: s.index)
    ]
    banner = (
        f'<p class="stamp">{_esc(stamp)}</p>' if stamp else ""
    )
    return (
        f'<article data-project="{_esc(dwg.project_name)}">'
        f'<h2>{_esc(dwg.project_name)}</h2>{banner}'
        f'{"".join(parts)}</article>'
    )
