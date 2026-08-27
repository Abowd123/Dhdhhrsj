"""
شبكة خطوط الجدران: التمثيل الذي يجعل التعديل البارامتري ممكنًا.

الغرفة تُعرَّف بأربعة معرّفات خطوط لا بأربعة أرقام. تحريك خط يحرّك كل
الغرف المرتبطة به معًا، فيستحيل التراكب أو الفراغ **بنيويًا** — لا
بالفحص بعد الحدث. وعدد متغيرات إعادة الحل يصير عدد الخطوط (≈20) بدل
4×عدد الغرف، فتُنجز السحبة في أجزاء من الثانية.

خطان على نفس الإحداثي لا يتلامسان = خطان مستقلان. هذا مقصود: وصلة T
يجب أن تبقى حرة في الانزياح، وإلا تجمّدت أجزاء لا علاقة لها بالسحبة.

موضع هذا الملف في `geometry/` لا `edit/` قرارٌ طبقي: `solver/refine.py`
يقرؤه للمحاذاة الرأسية، ولو بقي في `edit/` صار المُحلّل يعتمد على
المحرر — وهو اتجاه خاطئ.
"""
from __future__ import annotations
from dataclasses import dataclass
from planforge.codes.uk.detail_profile import DETAIL
from planforge.enums import Axis
from planforge.geometry.rect import Rect
from planforge.geometry.tiling import verify_tiling
from planforge.units import TOL

CLUSTER_TOL = DETAIL.line_cluster_tol_mm
"""
سماحية تجميع الإحداثيات المتقاربة في خط واحد.

مقايضة معلومة: في مخطط ضيّق قد يُدمج خطان متقاربان قصدًا فيتحرّكان معًا
بلا سبب. الرقم معامل لا ثابت — مرّر `cluster_tol=0` لتعطيل التجميع إن
كان تبليطك دقيقًا أصلًا.
"""


@dataclass(frozen=True, slots=True)
class WallLine:
    id: str
    axis: Axis
    coord: int
    is_boundary: bool
    lo_rooms: tuple[str, ...]    # غرف حدُّها الأعلى هذا الخط
    hi_rooms: tuple[str, ...]    # غرف حدُّها الأدنى هذا الخط
    span_lo: int
    span_hi: int

    @property
    def rooms(self) -> frozenset[str]:
        return frozenset(self.lo_rooms) | frozenset(self.hi_rooms)

    @property
    def movable(self) -> bool:
        return not self.is_boundary

    @property
    def span(self) -> int:
        return self.span_hi - self.span_lo


@dataclass(frozen=True, slots=True)
class RoomLines:
    room: str
    left: str
    right: str
    bottom: str
    top: str

    def line_ids(self) -> tuple[str, str, str, str]:
        return (self.left, self.right, self.bottom, self.top)


@dataclass
class Topology:
    """طوبولوجيا دور واحد. مُجمَّدة أثناء التعديل."""
    storey: int
    envelope: Rect
    lines: dict[str, WallLine]
    rooms: dict[str, RoomLines]

    def line(self, lid: str) -> WallLine:
        return self.lines[lid]

    def of_axis(self, axis: Axis) -> list[WallLine]:
        return sorted(
            (l for l in self.lines.values() if l.axis is axis),
            key=lambda l: (l.coord, l.span_lo),
        )

    def movable_lines(self) -> list[WallLine]:
        return [
            l for l in self.of_axis(Axis.V) + self.of_axis(Axis.H)
            if l.movable
        ]

    def lines_of_room(self, room_id: str) -> tuple[WallLine, ...]:
        return tuple(
            self.lines[lid] for lid in self.rooms[room_id].line_ids()
        )

    def neighbours(self, lid: str) -> tuple[int | None, int | None]:
        """
        أقرب خط قبله وبعده على نفس المحور مع تداخل في المدى.

        حدود الانزياح المعروضة في الواجهة. الحدود الصلبة يفرضها المُحلّل،
        فهذه للإرشاد البصري لا للصحة.
        """
        line = self.lines[lid]
        before: int | None = None
        after: int | None = None
        for other in self.of_axis(line.axis):
            if other.id == lid:
                continue
            if (other.span_hi <= line.span_lo
                    or line.span_hi <= other.span_lo):
                continue
            if other.coord < line.coord:
                before = (
                    other.coord if before is None
                    else max(before, other.coord)
                )
            elif other.coord > line.coord:
                after = (
                    other.coord if after is None
                    else min(after, other.coord)
                )
        return before, after


def _cluster(values: list[int], tol: int) -> dict[int, int]:
    """يُعيد {القيمة الأصلية: القيمة الممثِّلة} بعد تجميع المتقارب."""
    if not values:
        return {}
    ordered = sorted(set(values))
    if tol <= 0:
        return {v: v for v in ordered}
    out: dict[int, int] = {}
    group = [ordered[0]]
    for v in ordered[1:]:
        if v - group[-1] <= tol:
            group.append(v)
        else:
            rep = group[len(group) // 2]
            for g in group:
                out[g] = rep
            group = [v]
    rep = group[len(group) // 2]
    for g in group:
        out[g] = rep
    return out


def build_topology(
    storey: int,
    envelope: Rect,
    rects: dict[str, Rect],
    *,
    cluster_tol: int = CLUSTER_TOL,
) -> Topology:
    """
    اشتقاق شبكة الخطوط من تبليط غرف.

    يرفع `ValueError` إن لم يكن المُدخَل تبليطًا تامًّا، أو إن تعذّر ربط
    غرفة بأربعة خطوط. الحالتان تعنيان عيبًا في المُحلّل أو المحرر لا في
    المتطلب: النسخة السابقة كانت تفحص الربط وحده، وهو يصدق لأي مجموعة
    مستطيلات، فتمرّ تبليطات مكسورة بصمت.
    """
    verify_tiling(rects, envelope)
    xs = _cluster(
        [r.x for r in rects.values()] + [r.x2 for r in rects.values()]
        + [envelope.x, envelope.x2],
        cluster_tol,
    )
    ys = _cluster(
        [r.y for r in rects.values()] + [r.y2 for r in rects.values()]
        + [envelope.y, envelope.y2],
        cluster_tol,
    )

    lines: dict[str, WallLine] = {}
    assign: dict[tuple[str, str], str] = {}   # (room, side) → line id

    for axis, cmap, prefix in ((Axis.V, xs, "LX"), (Axis.H, ys, "LY")):
        # (الإحداثي الممثَّل) → [(span_lo, span_hi, room, side)]
        buckets: dict[int, list[tuple[int, int, str, str]]] = {}
        for rid, r in rects.items():
            if axis is Axis.V:
                buckets.setdefault(cmap[r.x], []).append(
                    (r.y, r.y2, rid, "hi")
                )
                buckets.setdefault(cmap[r.x2], []).append(
                    (r.y, r.y2, rid, "lo")
                )
            else:
                buckets.setdefault(cmap[r.y], []).append(
                    (r.x, r.x2, rid, "hi")
                )
                buckets.setdefault(cmap[r.y2], []).append(
                    (r.x, r.x2, rid, "lo")
                )

        n = 0
        for coord in sorted(buckets):
            entries = sorted(buckets[coord], key=lambda e: (e[0], e[2]))
            # تقموعات متلامسة: عدم التلامس ⇒ خطان مستقلان
            runs: list[list[tuple[int, int, str, str]]] = [[entries[0]]]
            reach = entries[0][1]
            for e in entries[1:]:
                if e[0] <= reach + TOL:
                    runs[-1].append(e)
                    reach = max(reach, e[1])
                else:
                    runs.append([e])
                    reach = e[1]

            if axis is Axis.V:
                bounds = (cmap[envelope.x], cmap[envelope.x2])
            else:
                bounds = (cmap[envelope.y], cmap[envelope.y2])

            for run in runs:
                n += 1
                lid = f"{prefix}{n:02d}"
                lines[lid] = WallLine(
                    id=lid, axis=axis, coord=coord,
                    is_boundary=coord in bounds,
                    lo_rooms=tuple(
                        sorted(e[2] for e in run if e[3] == "lo")
                    ),
                    hi_rooms=tuple(
                        sorted(e[2] for e in run if e[3] == "hi")
                    ),
                    span_lo=min(e[0] for e in run),
                    span_hi=max(e[1] for e in run),
                )
                for _lo, _hi, rid, side in run:
                    if axis is Axis.V:
                        key = (rid, "right" if side == "lo" else "left")
                    else:
                        key = (rid, "top" if side == "lo" else "bottom")
                    assign[key] = lid

    room_lines: dict[str, RoomLines] = {}
    for rid in rects:
        try:
            room_lines[rid] = RoomLines(
                room=rid,
                left=assign[(rid, "left")],
                right=assign[(rid, "right")],
                bottom=assign[(rid, "bottom")],
                top=assign[(rid, "top")],
            )
        except KeyError as exc:
            raise ValueError(
                f"تعذّر ربط الغرفة {rid} بخطوط الجدران — التبليط غير منتظم "
                f"(الحد الناقص: {exc})"
            ) from exc

    return Topology(storey, envelope, lines, room_lines)


def current_coords(topo: Topology) -> dict[str, int]:
    return {lid: l.coord for lid, l in topo.lines.items()}


def rects_from_lines(
    topo: Topology, coords: dict[str, int]
) -> dict[str, Rect]:
    """بناء مستطيلات الغرف من إحداثيات الخطوط."""
    out: dict[str, Rect] = {}
    for rid, rl in topo.rooms.items():
        x1, x2 = coords[rl.left], coords[rl.right]
        y1, y2 = coords[rl.bottom], coords[rl.top]
        out[rid] = Rect(x1, y1, x2 - x1, y2 - y1)
    return out
