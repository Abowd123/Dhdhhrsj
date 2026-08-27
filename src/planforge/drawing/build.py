"""المُنسِّق: Layout → Drawing."""
from __future__ import annotations
from planforge.drawing.annotate import build_dims, build_labels
from planforge.drawing.model import (
    ClearRoom, Drawing, StairDraw, StoreyDrawing,
)
from planforge.drawing.placement import place_openings, stair_geometry
from planforge.drawing.walls import (
    build_faces, clear_rooms, internal_envelope, merge_runs, party_lines,
    structural_lines,
)
from planforge.enums import RoomType
from planforge.model.brief import Brief
from planforge.model.layout import Layout

DRAWING_VERSION = "0.7.0"
STAIR_TYPES = frozenset({RoomType.STAIR, RoomType.LANDING})


def build_drawing(
    layout: Layout,
    brief: Brief,
    *,
    arabic_labels: bool = True,
    opening_hints: dict[str, float] | None = None,
) -> tuple[Drawing, list[str]]:
    """
    يُعيد (الرسم، مشاكل الفتحات).

    المشاكل تتحول إلى أخطاء `DRW-000` في `check_drawing`. لا تُبتلَع:
    فتحة لم تُحلّ تعني غرفة بلا باب في مخرج يبدو مكتملًا.
    """
    spec = brief.walls
    ordered = sorted(layout.storeys, key=lambda s: s.index)
    per_storey = [
        (s.envelope.to_rect(), {r.id: r.r for r in s.rooms}) for s in ordered
    ]
    sx, sy = structural_lines(per_storey)
    px, py = party_lines(brief.build_envelope, brief.setbacks)

    drawing = Drawing(
        project_name=layout.project_name,
        engine_version=f"{layout.engine_version}/{DRAWING_VERSION}",
    )
    all_problems: list[str] = []

    for st in ordered:
        env = st.envelope.to_rect()
        rects = {r.id: r.r for r in st.rooms}
        types = {r.id: r.type for r in st.rooms}

        faces = build_faces(
            rects, types, env, spec,
            structural_x=sx, structural_y=sy,
            protected_stair=st.protected_stair,
            party_x=px, party_y=py,
        )
        runs = merge_runs(faces)
        clear = clear_rooms(rects, faces)
        placed, problems = place_openings(
            st, faces, clear, brief, hints=opening_hints
        )
        all_problems.extend(f"[دور {st.index}] {p}" for p in problems)

        rooms = [
            ClearRoom(
                id=i, type=types[i],
                x=clear[i].x, y=clear[i].y, w=clear[i].w, h=clear[i].h,
                centerline_area_mm2=rects[i].area,
                ceiling_height_mm=(
                    st.room(i).ceiling_height_mm
                    or brief.storey_spec(st.index).floor_to_ceiling_mm
                ),
                storage_area_mm2=st.room(i).storage_area_mm2,
            )
            for i in sorted(clear)
        ]

        stair: StairDraw | None = None
        if brief.is_multi_storey:
            src = next(
                (r for r in st.rooms if r.type is RoomType.STAIR), None
            )
            if src is not None and src.id in clear:
                rect = clear[src.id]
                risers, horiz, n, rise, going = stair_geometry(
                    src.id, rect, brief.max_floor_to_floor_mm
                )
                stair = StairDraw(
                    room=src.id,
                    rect=(rect.x, rect.y, rect.w, rect.h),
                    risers=risers, horizontal=horiz,
                    n_risers=n, rise_mm=rise, going_mm=going,
                )

        inner = internal_envelope(env, spec)
        sd = StoreyDrawing(
            index=st.index,
            envelope=(inner.x, inner.y, inner.w, inner.h),
            runs=runs, faces=faces, openings=placed, rooms=rooms,
            protected_stair=st.protected_stair, stair=stair,
        )
        sd.dims = build_dims(env, runs, placed)
        sd.labels = build_labels(rooms, arabic_labels)
        drawing.storeys.append(sd)

    return drawing, all_problems
