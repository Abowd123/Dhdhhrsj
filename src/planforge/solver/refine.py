"""
من تبليط إلى مخطط: الأبواب والنوافذ والمحاذاة الرأسية والتخزين.

المُحلّل يُخرج مستطيلات فقط. هذه الوحدة تجيب على ما لا يستطيع المُحلّل
الإجابة عنه بكفاءة:
  • أي غرفتين تشتركان جدارًا يكفي لباب؟ وأي شجرة أبواب تصل كل غرفة
    بالمدخل بأقصر مسار مُرجَّح؟
  • أي جدار خارجي يحمل نافذة، وبأي عرض تتحقّق نسبة ADF؟
  • هل خطوط الجدران متحاذية بين الأدوار، وهل تُقرَّب إن تقاربت؟
  • كم من تخزين NDSS §9 يُنسب إلى كل غرفة نوم؟

المواضع هنا على **خطوط المراكز**. طبقة الرسم تعيد حلّها على الجدران
الحقيقية بكتفٍ لكل فتحة. لا تعتمد على أرقام هذا الملف كمواضع نهائية.
"""
from __future__ import annotations
import heapq
from math import inf
from planforge.codes.uk.detail_profile import DETAIL
from planforge.codes.uk.profile import UK
from planforge.enums import (
    Axis, BEDROOMS, CIRCULATION, HABITABLE, NEEDS_PURGE_VENT, OpeningKind,
    RoomType,
)
from planforge.geometry.rect import Rect
from planforge.geometry.tiling import Segment, boundary_segments, verify_tiling
from planforge.model.brief import Brief
from planforge.model.layout import (
    Opening, RectModel, RoomInstance, StoreyLayout,
)
from planforge.solver.storey import StoreySolution

FRAME_MM = DETAIL.door_frame_mm
JAMB_NIB_MM = DETAIL.jamb_nib_min_mm
GEN_VENT_RATIO = 1 / 16      # هامش أمان فوق 1/20 في ADF — النافذة تُقلَّص لاحقًا
WINDOW_HEAD_MM = DETAIL.window_head_mm
WINDOW_SILL_MM = 900
ESCAPE_SILL_MM = 850
WINDOW_CORNER_MM = DETAIL.window_corner_offset_mm
OPENABLE_FRACTION = DETAIL.window_openable_fraction
ALIGN_SNAP_MM = 150          # تقريب خطوط الأدوار المتقاربة
STORAGE_CAP_RATIO = 0.10     # أقصى ما يُنسب لغرفة نوم من مساحتها كتخزين

CIRC_COST = 1
PRIVATE_COST = 12            # عبور غرفة خاصة للوصول إلى أخرى عيبٌ تخطيطي


def _door_need(brief: Brief) -> int:
    return (
        UK.door_min_clear_width[brief.access_standard]
        + 2 * FRAME_MM + 2 * JAMB_NIB_MM
    )


def _entrance(types: dict[str, RoomType]) -> str | None:
    for pref in (
        RoomType.ENTRANCE_HALL, RoomType.HALL,
        RoomType.LOBBY, RoomType.LANDING,
    ):
        for rid, t in sorted(types.items()):
            if t is pref:
                return rid
    return next(iter(sorted(types)), None)


def _door_tree(
    segs: list[Segment], types: dict[str, RoomType], need: int, root: str
) -> tuple[list[tuple[str, str, int]], list[str]]:
    """
    شجرة أبواب تصل كل غرفة بالمدخل بأقصر مسار مُرجَّح — عبور غرف
    غير الحركة تُكلَّف أكثر. المسار الناتج أمثل لا تقريبي، وهذا يظهر في
    المخططات الكبيرة حيث البحث بالعرض يُخرج شجرة ملتوية.
    """
    graph: dict[str, list[tuple[str, int]]] = {r: [] for r in types}
    for s in segs:
        if s.a is None or s.b is None or s.length < need:
            continue
        if s.a not in graph or s.b not in graph:
            continue
        cost = (
            CIRC_COST
            if (types.get(s.a) in CIRCULATION or types.get(s.b) in CIRCULATION)
            else PRIVATE_COST
        )
        graph[s.a].append((s.b, cost))
        graph[s.b].append((s.a, cost))
    for adj in graph.values():
        adj.sort(key=lambda e: (e[1], e[0]))

    dist: dict[str, int] = {root: 0}
    parent: dict[str, tuple[str, int]] = {}
    heap: list[tuple[int, str]] = [(0, root)]
    while heap:
        d, cur = heapq.heappop(heap)
        if d > dist.get(cur, inf):
            continue
        for nxt, cost in graph[cur]:
            nd = d + cost
            if nd < dist.get(nxt, inf):
                dist[nxt] = nd
                parent[nxt] = (cur, cost)
                heapq.heappush(heap, (nd, nxt))

    edges = [
        (p, child, cost) for child, (p, cost) in sorted(parent.items())
    ]
    orphans = sorted(set(types) - set(dist))
    return edges, orphans


def derive_openings(
    sol: StoreySolution, brief: Brief, *, protected_stair: bool
) -> tuple[list[Opening], list[str]]:
    """يُعيد (الفتحات على خطوط المراكز، المشاكل)."""
    types = sol.types
    rects = sol.rects
    env = sol.envelope
    segs = boundary_segments(rects, env)
    need = _door_need(brief)
    problems: list[str] = []
    out: list[Opening] = []
    n = 0

    root = _entrance(types)
    if root is None:
        return [], [f"دور {sol.index}: بلا غرف"]

    stair_ids = {
        r for r, t in types.items()
        if t in {RoomType.STAIR, RoomType.LANDING}
    }

    # ── باب خارجي في دور الدخول ──
    if sol.index == brief.entrance_storey:
        ext_root = [
            s for s in segs
            if (s.a is None and s.b == root) or (s.b is None and s.a == root)
        ]
        if ext_root:
            n += 1
            out.append(Opening(
                id=f"D{sol.index}{n:02d}", kind=OpeningKind.DOOR,
                storey=sol.index, a=root, b=None,
                clear_width_mm=max(
                    900, UK.door_min_clear_width[brief.access_standard]
                ),
            ))
        else:
            problems.append(
                f"دور {sol.index}: غرفة الدخول {root} بلا واجهة خارجية — "
                f"لا باب رئيسي"
            )

    # ── أبواب داخلية ──
    edges, orphans = _door_tree(segs, types, need, root)
    for a, b, _cost in edges:
        n += 1
        fire = protected_stair and ((a in stair_ids) != (b in stair_ids))
        out.append(Opening(
            id=f"D{sol.index}{n:02d}",
            kind=OpeningKind.FIRE_DOOR if fire else OpeningKind.DOOR,
            storey=sol.index, a=a, b=b,
            clear_width_mm=UK.door_min_clear_width[brief.access_standard],
        ))
    for rid in orphans:
        problems.append(
            f"دور {sol.index}: الغرفة {rid} ({types[rid]}) لا تشترك جدارًا "
            f"يكفي لباب ({need} مم) مع أي غرفة موصولة"
        )

    # ── نوافذ ──
    spec = brief.storey_spec(sol.index)
    upper_below_threshold = (
        sol.index != brief.entrance_storey
        and spec.floor_level_mm <= UK.protected_stair_threshold
    )
    esc_lo, esc_hi = UK.escape_window_sill_range
    w = 0
    for rid, r in sorted(rects.items()):
        rtype = types[rid]
        if rtype not in HABITABLE and rtype not in NEEDS_PURGE_VENT:
            continue
        ext = [
            s for s in segs
            if (s.a is None and s.b == rid) or (s.b is None and s.a == rid)
        ]
        if not ext:
            if rtype in HABITABLE:
                problems.append(
                    f"دور {sol.index}: الغرفة المعيشية {rid} بلا واجهة خارجية"
                )
            continue

        # نافذة هروب لكل غرفة سكن في دور علوي دون حد السلّم المحمي —
        # ADB-005 يطلبها لـHABITABLE كلها، لا لغرف النوم وحدها.
        escape = upper_below_threshold and rtype in HABITABLE
        sill = (
            min(max(ESCAPE_SILL_MM, esc_lo), esc_hi)
            if escape else WINDOW_SILL_MM
        )
        height = max(1, WINDOW_HEAD_MM - sill)
        need_open = int(r.area * GEN_VENT_RATIO)
        want = -(-need_open // max(1, int(height * OPENABLE_FRACTION)))
        if escape:
            want = max(
                want,
                UK.escape_window_min_dim,
                -(-UK.escape_window_min_area
                  // max(1, int(height * OPENABLE_FRACTION))),
            )

        face = max(ext, key=lambda s: (s.length, s.coord))
        avail = face.length - 2 * WINDOW_CORNER_MM
        if avail < 600:
            problems.append(
                f"دور {sol.index}: واجهة {rid} طولها {face.length} مم — "
                f"لا تستوعب نافذة"
            )
            continue
        width = min(max(600, (want // 50) * 50 + 50), (avail // 50) * 50)
        openable = int(width * height * OPENABLE_FRACTION)

        w += 1
        out.append(Opening(
            id=f"W{sol.index}{w:02d}",
            kind=(
                OpeningKind.ESCAPE_WINDOW if escape else OpeningKind.WINDOW
            ),
            storey=sol.index, a=rid, b=None,
            clear_width_mm=width, sill_mm=sill,
            openable_area_mm2=openable,
        ))
        if escape and openable < UK.escape_window_min_area:
            problems.append(
                f"دور {sol.index}: نافذة هروب {rid} تبلغ {openable} مم² فقط "
                f"— الواجهة لا تكفي"
            )
    return out, problems


def align_storeys(
    sols: list[StoreySolution], *, snap_mm: int = ALIGN_SNAP_MM
) -> list[str]:
    """
    تقريب خطوط الجدران المتقاربة بين الأدوار إلى إحداثي واحد.

    مكسبه إنشائي مباشر: `structural_lines` تشترط وجود الخط في كل الأدوار
    داخل سماحية 60 مم. خطان يفترقان 90 مم يفقدان تصنيفهما حاملًا بلا
    سبب. يُعدّل المستطيلات في مكانها ويُعيد وصفًا لما تحرّك.
    """
    if len(sols) < 2:
        return []

    from planforge.geometry.lines import build_topology

    notes: list[str] = []
    base = sols[0]
    base_topo = build_topology(base.index, base.envelope, base.rects)
    anchors = {
        Axis.V: sorted({l.coord for l in base_topo.of_axis(Axis.V)}),
        Axis.H: sorted({l.coord for l in base_topo.of_axis(Axis.H)}),
    }

    for sol in sols[1:]:
        topo = build_topology(sol.index, sol.envelope, sol.rects)
        moves: dict[tuple[Axis, int], int] = {}
        for axis in (Axis.V, Axis.H):
            for line in topo.of_axis(axis):
                if line.is_boundary:
                    continue
                near = [
                    a for a in anchors[axis]
                    if 0 < abs(a - line.coord) <= snap_mm
                ]
                if not near:
                    continue
                moves[(axis, line.coord)] = min(
                    near, key=lambda a: (abs(a - line.coord), a)
                )
        if not moves:
            continue

        # التقريب يُطبَّق كوحدة أو لا يُطبَّق. تحريك بعض الغرف وتثبيت
        # البقية — كما كان يفعل `continue` على الغرفة المُفناة — يفتح
        # فراغًا يظهر في GEO-003 برسالة لا تدلّ على سببه.
        candidate: dict[str, Rect] = {}
        failure = ""
        for rid, r in sol.rects.items():
            x1 = moves.get((Axis.V, r.x), r.x)
            x2 = moves.get((Axis.V, r.x2), r.x2)
            y1 = moves.get((Axis.H, r.y), r.y)
            y2 = moves.get((Axis.H, r.y2), r.y2)
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                failure = f"يُفني الغرفة {rid}"
                break
            candidate[rid] = Rect(x1, y1, x2 - x1, y2 - y1)

        if not failure:
            try:
                verify_tiling(candidate, sol.envelope)
            except ValueError as exc:
                failure = str(exc)

        if failure:
            notes.append(
                f"دور {sol.index}: أُلغي تقريب {len(moves)} خطًا إلى "
                f"محاذاة الدور {base.index} — {failure}"
            )
            continue

        sol.rects = candidate
        # النجاح لا يُبلَّغ: كل ملاحظة تصير SOL-001 بشدّة WARN، ووزنها
        # في الترتيب سالب — فكان التقريب الناجح يُعاقب المخطط الذي
        # حسّنه إنشائيًا.
    return notes


def assign_storage(layouts: list[StoreyLayout], brief: Brief) -> list[str]:
    """
    توزيع تخزين NDSS §9 على غرف النوم.

    سمة لا هندسة: التخزين المدمج خزانة في جدار، لا غرفة في التبليط.
    المخازن المخصَّصة تُحسب أولًا، والباقي يُقسَّم بسقف نسبةٍ من مساحة
    كل غرفة — فإن لم يكفِ، يظهر النقص في `NDSS-004` بدل أن يُخبّأ.
    """
    required = UK.storage_required(brief.n_bedrooms)
    if not required:
        return []
    dedicated = sum(
        r.rect.to_rect().area
        for st in layouts for r in st.rooms
        if r.type is RoomType.STORAGE
    )
    remaining = required - dedicated
    if remaining <= 0:
        return []
    beds = [
        r for st in layouts for r in st.rooms if r.type in BEDROOMS
    ]
    if not beds:
        return [
            "لا غرف نوم لنسبة التخزين المدمج إليها — سيظهر النقص في NDSS-004"
        ]
    share = -(-remaining // len(beds))
    assigned = 0
    for r in beds:
        give = min(share, int(r.rect.to_rect().area * STORAGE_CAP_RATIO))
        r.storage_area_mm2 = give
        assigned += give
    if dedicated + assigned < required:
        return [
            f"التخزين المتاح {dedicated + assigned} مم² دون المطلوب "
            f"{required} مم² — أضف مخزنًا مخصَّصًا أو كبّر غرف النوم"
        ]
    return []


def to_storey_layout(
    sol: StoreySolution, openings: list[Opening], *, protected_stair: bool
) -> StoreyLayout:
    return StoreyLayout(
        index=sol.index,
        envelope=RectModel.of(sol.envelope),
        rooms=[
            RoomInstance(
                id=rid, type=sol.types[rid], storey=sol.index,
                rect=RectModel.of(r),
            )
            for rid, r in sorted(sol.rects.items())
        ],
        openings=openings,
        protected_stair=protected_stair,
    )


def refine(
    sols: list[StoreySolution], brief: Brief, *, protected_stair: bool
) -> tuple[list[StoreyLayout], list[str]]:
    """المدخل الوحيد الذي يستدعيه `generate.py`."""
    ordered = sorted(sols, key=lambda s: s.index)
    problems = align_storeys(ordered)
    layouts: list[StoreyLayout] = []
    for sol in ordered:
        ops, probs = derive_openings(
            sol, brief, protected_stair=protected_stair
        )
        problems.extend(probs)
        layouts.append(
            to_storey_layout(sol, ops, protected_stair=protected_stair)
        )
    problems.extend(assign_storage(layouts, brief))
    for st in layouts:
        spec = brief.storey_spec(st.index)
        for r in st.rooms:
            r.ceiling_height_mm = spec.floor_to_ceiling_mm
    return layouts, problems
