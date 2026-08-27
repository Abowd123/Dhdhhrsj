"""
إعادة الحل بطوبولوجيا مُجمَّدة.

الفرق الجوهري عن مُحلّل التبليط: الهدف هنا **تقليل الحركة عن الحالة
الحالية**، والمساحة قيد. في المُحلّل كان العكس تمامًا. وهذا ما يجعل
السحبة محلّية ومتوقَّعة: يتحرّك ما يجب أن يتحرّك فقط، بدل أن يُقفز
المخطط كله عند كل تعديل فيفقد المهندس السيطرة.

الخط المسحوب يُحترم بوزن عالٍ لا بقيد صلب: فنُعيد أقرب حل ممكن مع رسالة
عمّا تحرّك، بدل الفشل الصامت عند موضع مستحيل.
"""
from __future__ import annotations
from dataclasses import dataclass
from ortools.sat.python import cp_model
from planforge.codes.uk.profile import UK
from planforge.enums import Axis, CIRCULATION, RoomType
from planforge.geometry.lines import Topology, rects_from_lines
from planforge.geometry.rect import Rect
from planforge.model.brief import Brief
from planforge.units import m2

GRID = 10          # مم — دقة المحرر أعلى من دقة التبليط
STIFFNESS = 1      # وزن حركة أي خط غير مسحوب
PINNED_W = 10_000  # وزن احترام الخط المسحوب
AREA_W = 120       # وزن الوصول إلى مساحة مستهدفة

FLOOR_FALLBACK_MM = 700
CIRC_AREA_FLOOR = m2(1.5)
CIRC_AREA_CEIL = m2(60.0)


@dataclass(frozen=True, slots=True)
class RoomBounds:
    min_dim: int
    min_area: int
    max_area: int
    max_aspect: float


@dataclass
class ResolveResult:
    rects: dict[str, Rect] | None
    moved: dict[str, int]        # معرّف الخط → الانزياح بالمم
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.rects is not None


def bounds_from_brief(
    brief: Brief, room_types: dict[str, RoomType]
) -> dict[str, RoomBounds]:
    """
    حدود كل غرفة في المحرر.

    المجالات أوسع مما في المُحلّل قصدًا: المهندس يعرف ما يريد، والتدقيق
    يحكم بعده. تضييقها هنا يمنع تعديلات صالحة بحجّة أنها تخالف مستهدفًا
    كان تقديريًا أصلًا.
    """
    by_id = {r.id: r for r in brief.rooms}
    out: dict[str, RoomBounds] = {}
    for rid, rtype in room_types.items():
        req = by_id.get(rid)
        floor = UK.practical_min_width.get(rtype, FLOOR_FALLBACK_MM)
        if req is not None and req.min_width_mm:
            floor = max(floor, req.min_width_mm)
        if req is not None:
            lo = req.min_area_mm2 or int(req.target_area_mm2 * 0.60)
            hi = req.max_area_mm2 or int(req.target_area_mm2 * 2.20)
        else:
            lo, hi = m2(1.0), m2(120.0)
        if rtype in CIRCULATION:
            lo = min(lo, CIRC_AREA_FLOOR)
            hi = max(hi, CIRC_AREA_CEIL)
        out[rid] = RoomBounds(
            min_dim=floor,
            min_area=lo,
            max_area=hi,
            max_aspect=float(
                req.max_aspect if req and req.max_aspect else 8.0
            ),
        )
    return out


def resolve(
    topo: Topology,
    bounds: dict[str, RoomBounds],
    *,
    pinned: dict[str, int] | None = None,
    area_targets: dict[str, int] | None = None,
    time_limit_s: float = 3.0,
    deterministic: bool = False,
) -> ResolveResult:
    """
    `pinned`       : {معرّف الخط: الإحداثي المطلوب}.
    `area_targets` : {معرّف الغرفة: مساحة مستهدفة} — لعملية تغيير الحجم.
    """
    pinned = pinned or {}
    area_targets = area_targets or {}
    env = topo.envelope
    m = cp_model.CpModel()

    lo_x, hi_x = env.x // GRID, env.x2 // GRID
    lo_y, hi_y = env.y // GRID, env.y2 // GRID
    span_x, span_y = hi_x - lo_x, hi_y - lo_y
    if span_x <= 0 or span_y <= 0:
        return ResolveResult(None, {}, "المظروف أصغر من خطوة الشبكة")

    off_grid = [
        v for v in (env.x, env.y, env.x2, env.y2) if v % GRID
    ]
    if off_grid:
        return ResolveResult(
            None, {},
            f"حدود المظروف {off_grid} غير قابلة للقسمة على شبكة المحرر "
            f"({GRID} مم) — اجعل الارتدادات مضاعفات {GRID}",
        )

    var: dict[str, cp_model.IntVar] = {}
    for lid, line in topo.lines.items():
        lo, hi = (lo_x, hi_x) if line.axis is Axis.V else (lo_y, hi_y)
        v = m.new_int_var(lo, hi, f"c_{lid}")
        var[lid] = v
        if line.is_boundary:
            m.add(v == line.coord // GRID)

    terms: list[cp_model.LinearExpr] = []
    xints, yints = [], []
    cell = GRID * GRID

    for rid, rl in topo.rooms.items():
        b = bounds.get(rid)
        if b is None:
            return ResolveResult(
                None, {}, f"لا حدود معروفة للغرفة {rid}"
            )
        L, R = var[rl.left], var[rl.right]
        B, T = var[rl.bottom], var[rl.top]

        w = m.new_int_var(1, span_x, f"w_{rid}")
        h = m.new_int_var(1, span_y, f"h_{rid}")
        m.add(w == R - L)
        m.add(h == T - B)

        floor = max(1, -(-b.min_dim // GRID))
        m.add(w >= floor)
        m.add(h >= floor)

        area = m.new_int_var(1, span_x * span_y, f"a_{rid}")
        m.add_multiplication_equality(area, [w, h])
        m.add(area >= max(1, b.min_area // cell))
        m.add(area <= -(-b.max_area // cell))

        cap = int(b.max_aspect * 100)
        m.add(w * 100 <= h * cap)
        m.add(h * 100 <= w * cap)

        xints.append(m.new_interval_var(L, w, R, f"ix_{rid}"))
        yints.append(m.new_interval_var(B, h, T, f"iy_{rid}"))

        if rid in area_targets:
            dev = m.new_int_var(0, span_x * span_y, f"dev_{rid}")
            m.add_abs_equality(dev, area - area_targets[rid] // cell)
            terms.append(AREA_W * dev)

    # شبكة أمان: التبليط والتفارق مضمونان بالتمثيل، ونفرضهما صريحًا
    # لأن سقوطهما يعني عيبًا في بناء الطوبولوجيا لا في التعديل
    m.add_no_overlap_2d(xints, yints)

    for lid, line in topo.lines.items():
        if line.is_boundary:
            continue
        want = pinned.get(lid, line.coord) // GRID
        d = m.new_int_var(0, span_x + span_y, f"d_{lid}")
        m.add_abs_equality(d, var[lid] - want)
        terms.append((PINNED_W if lid in pinned else STIFFNESS) * d)

    m.minimize(sum(terms) if terms else 0)

    from planforge.solver.determinism import Limits, apply_limits

    solver = cp_model.CpSolver()
    apply_limits(solver, Limits(
        deterministic=deterministic,
        time_limit_s=time_limit_s,
        workers=4,
    ))
    if solver.solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ResolveResult(
            None, {},
            "تعذّر إيجاد حل يحفظ الأبعاد الدنيا ومجالات المساحة عند هذا "
            "الموضع",
        )

    coords = {lid: solver.value(v) * GRID for lid, v in var.items()}
    moved = {
        lid: coords[lid] - line.coord
        for lid, line in topo.lines.items()
        if coords[lid] != line.coord
    }
    return ResolveResult(rects_from_lines(topo, coords), moved)
