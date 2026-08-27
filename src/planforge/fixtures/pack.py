"""
حزم التجهيزات داخل غرفة، ومنه استنباط أصغر غرفة ممكنة.

النموذج (CP-SAT):
  • لكل تجهيز أربعة اتجاهات محتملة (الظهر إلى أحد الجدران)، مُرمَّزة
    بفترات اختيارية بحرف حضور لكل اتجاه، و`exactly_one` عليها.
  • أجسام التجهيزات + مربعات دوران الأبواب + خلوص الدوران في مجموعة
    `no_overlap_2d` واحدة.
  • حيّز استخدام تجهيز يُمنع تراكبه مع **جسم** تجهيز آخر، ويُسمح تراكبه
    مع حيّز آخر — وهذا هو العرف في رسومات ADM، لا تسهيلًا.

الهدف: تقريب التجهيزات المحتاجة صرفًا من نقطة عمود المواسير.

قراران يستحقان الذكر لأن العكس يبدو أصحّ:

١. **الحيّز يحتوي واجهة التجهيز، ولا يتمركز عليها.** التمركز
   (`2·ax == x + x2 − aw`) يفرض تكافؤًا حسابيًا: بعرض تجهيز فردي وحيّز
   زوجي بوحدات الشبكة يصير الطرفان مختلفَي الزوجية، والقيد متعذّر لأي
   موضع. مغسلة 550 مم بحيّز 700 مم على شبكة 50 مم تُسقط الغرفة كلها.
   الاحتواء يعطي المعنى نفسه بقيدين خطّيين بلا تعذّر.

٢. **التقريب متحفّظ في اتجاه واحد.** الغرفة تُقلَّص إلى الشبكة والعوائق
   تُوسَّع. غرفة تفشل بفارق 30 مم قد تنجح على شبكة أدق — والخطأ في
   اتجاه الرفض، وهو الصحيح لأداة تدقيق.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from ortools.sat.python import cp_model
from planforge.codes.uk.detail_profile import DETAIL
from planforge.codes.uk.fixtures_profile import FIX, FixtureSpec
from planforge.enums import AccessStandard
from planforge.fixtures.result import MinEnvelope

GRID = DETAIL.pack_grid_mm
MAX_SIDE_MM = 8000
LIMIT = MAX_SIDE_MM // GRID
DEFAULT_DOOR_MM = 900


def _up(v: int) -> int:
    return -(-v // GRID)


def _down(v: int) -> int:
    return v // GRID


@dataclass(frozen=True, slots=True)
class Placement:
    code: str
    x: int
    y: int
    w: int
    h: int
    rotation_deg: int
    activity: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class PackResult:
    placements: tuple[Placement, ...]
    ok: bool
    reason: str = ""
    minimum: MinEnvelope | None = None


class _Cand:
    """مرشّح (تجهيز، اتجاه): فترات اختيارية للجسم وحيّز الاستخدام."""

    __slots__ = (
        "rot", "lit", "bw", "bh", "aw", "ah",
        "x", "y", "x2", "y2", "ax", "ay", "ax2", "ay2", "xi", "yi",
    )

    def __init__(
        self,
        m: cp_model.CpModel,
        tag: str,
        rot: int,
        spec: FixtureSpec,
        rx, ry, rw, rh,
        pin_to_wall: bool,
    ) -> None:
        self.rot = rot
        self.lit = m.new_bool_var(f"p_{tag}")

        fw, fd = _up(spec.w), _up(spec.d)
        aw_face = _up(max(spec.activity_w, spec.w))
        ad = _up(spec.activity_d)

        horiz = rot in (0, 180)
        self.bw = fw if horiz else fd
        self.bh = fd if horiz else fw
        self.aw = aw_face if horiz else ad
        self.ah = ad if horiz else aw_face

        self.x = m.new_int_var(0, LIMIT, f"x_{tag}")
        self.y = m.new_int_var(0, LIMIT, f"y_{tag}")
        self.x2 = m.new_int_var(0, LIMIT, f"x2_{tag}")
        self.y2 = m.new_int_var(0, LIMIT, f"y2_{tag}")
        m.add(self.x2 == self.x + self.bw)
        m.add(self.y2 == self.y + self.bh)

        lit = self.lit
        m.add(self.x >= rx).only_enforce_if(lit)
        m.add(self.y >= ry).only_enforce_if(lit)
        m.add(self.x2 <= rx + rw).only_enforce_if(lit)
        m.add(self.y2 <= ry + rh).only_enforce_if(lit)

        if pin_to_wall:
            if rot == 0:
                m.add(self.y == ry).only_enforce_if(lit)
            elif rot == 90:
                m.add(self.x == rx).only_enforce_if(lit)
            elif rot == 180:
                m.add(self.y2 == ry + rh).only_enforce_if(lit)
            else:
                m.add(self.x2 == rx + rw).only_enforce_if(lit)

        # ── حيّز الاستخدام أمام الواجهة ──
        self.ax = m.new_int_var(0, LIMIT, f"ax_{tag}")
        self.ay = m.new_int_var(0, LIMIT, f"ay_{tag}")
        self.ax2 = m.new_int_var(0, LIMIT, f"ax2_{tag}")
        self.ay2 = m.new_int_var(0, LIMIT, f"ay2_{tag}")
        m.add(self.ax2 == self.ax + self.aw)
        m.add(self.ay2 == self.ay + self.ah)

        if rot == 0:
            m.add(self.ay == self.y2)
            self._cover_x(m)
        elif rot == 180:
            m.add(self.ay2 == self.y)
            self._cover_x(m)
        elif rot == 90:
            m.add(self.ax == self.x2)
            self._cover_y(m)
        else:
            m.add(self.ax2 == self.x)
            self._cover_y(m)

        m.add(self.ax >= rx).only_enforce_if(lit)
        m.add(self.ay >= ry).only_enforce_if(lit)
        m.add(self.ax2 <= rx + rw).only_enforce_if(lit)
        m.add(self.ay2 <= ry + rh).only_enforce_if(lit)

        self.xi = m.new_optional_interval_var(
            self.x, self.bw, self.x2, lit, f"bx_{tag}"
        )
        self.yi = m.new_optional_interval_var(
            self.y, self.bh, self.y2, lit, f"by_{tag}"
        )

    def _cover_x(self, m: cp_model.CpModel) -> None:
        """الحيّز يغطّي عرض الواجهة — بديل التمركز بلا قيد زوجية."""
        m.add(self.ax <= self.x)
        m.add(self.ax2 >= self.x2)

    def _cover_y(self, m: cp_model.CpModel) -> None:
        m.add(self.ay <= self.y)
        m.add(self.ay2 >= self.y2)

    def body(self) -> tuple:
        return (self.x, self.y, self.x2, self.y2)

    def zone(self) -> tuple:
        return (self.ax, self.ay, self.ax2, self.ay2)


def _disjoint(
    m: cp_model.CpModel, A: tuple, B: tuple, lits: list, tag: str
) -> None:
    """A و B مستطيلان (x, y, x2, y2)؛ يُفرض التفارق حين تصدق كل lits."""
    ax, ay, ax2, ay2 = A
    bx, by, bx2, by2 = B
    sides = []
    for name, left, right in (
        ("e", ax2, bx), ("w", bx2, ax), ("n", ay2, by), ("s", by2, ay)
    ):
        s = m.new_bool_var(f"d_{tag}_{name}")
        m.add(left <= right).only_enforce_if(s)
        sides.append(s)
    m.add_bool_or([*(l.negated() for l in lits), *sides])


def _rotations(spec: FixtureSpec) -> tuple[int, ...]:
    """
    الاتجاهات الممكنة. التجهيز الحر (طاولة) متناظر، فاتجاهان يكفيان —
    كسر تناظر يوفّر نصف المتغيرات بلا تضييق فضاء الحل.
    """
    return (0, 90, 180, 270) if spec.against_wall else (0, 90)


def _build(
    m: cp_model.CpModel,
    codes: tuple[str, ...],
    rx: int, ry: int, rw, rh,
    door_zones: list[tuple[int, int, int, int]],
    turning: int,
    swing_clear_activity: bool,
) -> dict[str, list[_Cand]]:
    cands: dict[str, list[_Cand]] = {}
    xints: list = []
    yints: list = []

    for i, code in enumerate(codes):
        spec = FIX.spec(code)
        tag_base = f"{code}{i}"
        group = [
            _Cand(
                m, f"{tag_base}_{r}", r, spec, rx, ry, rw, rh,
                pin_to_wall=spec.against_wall,
            )
            for r in _rotations(spec)
        ]
        m.add_exactly_one(c.lit for c in group)
        cands[tag_base] = group
        xints.extend(c.xi for c in group)
        yints.extend(c.yi for c in group)

    # دوران الأبواب: صناديق ثابتة، تُوسَّع إلى الشبكة (اتجاه متحفّظ)
    zones: list[tuple] = []
    for j, (dx, dy, dw, dh) in enumerate(door_zones):
        zx, zy = _down(dx), _down(dy)
        zx2, zy2 = _up(dx + dw), _up(dy + dh)
        xints.append(
            m.new_interval_var(zx, zx2 - zx, zx2, f"dzx{j}")
        )
        yints.append(
            m.new_interval_var(zy, zy2 - zy, zy2, f"dzy{j}")
        )
        zones.append((zx, zy, zx2, zy2))

    # خلوص الدوران: مربع حر لا يلامس شيئًا
    turn: tuple | None = None
    if turning:
        t = _up(turning)
        tx = m.new_int_var(0, LIMIT, "tx")
        ty = m.new_int_var(0, LIMIT, "ty")
        m.add(tx >= rx)
        m.add(ty >= ry)
        m.add(tx + t <= rx + rw)
        m.add(ty + t <= ry + rh)
        xints.append(m.new_interval_var(tx, t, tx + t, "tix"))
        yints.append(m.new_interval_var(ty, t, ty + t, "tiy"))
        turn = (tx, ty, tx + t, ty + t)

    m.add_no_overlap_2d(xints, yints)

    tags = list(cands)
    for a in tags:
        for b in tags:
            if a == b:
                continue
            for ca in cands[a]:
                for cb in cands[b]:
                    _disjoint(
                        m, ca.zone(), cb.body(), [ca.lit, cb.lit],
                        f"{a}{ca.rot}_{b}{cb.rot}",
                    )

    if swing_clear_activity:
        for j, zone in enumerate(zones):
            for a in tags:
                for ca in cands[a]:
                    _disjoint(
                        m, ca.zone(), zone, [ca.lit],
                        f"sw{j}_{a}{ca.rot}",
                    )

    if turn is not None:
        for a in tags:
            for ca in cands[a]:
                _disjoint(m, ca.zone(), turn, [ca.lit], f"tn_{a}{ca.rot}")

    return cands


def _drain_objective(
    m: cp_model.CpModel,
    cands: dict[str, list[_Cand]],
    codes: tuple[str, ...],
    stack: tuple[int, int],
) -> None:
    """تقريب التجهيزات المحتاجة صرفًا من عمود المواسير."""
    sx, sy = _down(stack[0]), _down(stack[1])
    terms: list = []
    for i, code in enumerate(codes):
        if not FIX.needs_drain(code):
            continue
        for c in cands[f"{code}{i}"]:
            dx = m.new_int_var(0, LIMIT, f"sdx_{code}{i}_{c.rot}")
            dy = m.new_int_var(0, LIMIT, f"sdy_{code}{i}_{c.rot}")
            m.add_abs_equality(dx, c.x - sx)
            m.add_abs_equality(dy, c.y - sy)
            pen = m.new_int_var(0, 2 * LIMIT, f"sd_{code}{i}_{c.rot}")
            m.add(pen == dx + dy).only_enforce_if(c.lit)
            m.add(pen == 0).only_enforce_if(c.lit.negated())
            terms.append(pen)
    if terms:
        m.minimize(sum(terms))


def pack_room(
    *,
    room_rect: tuple[int, int, int, int],
    codes: tuple[str, ...],
    door_zones: list[tuple[int, int, int, int]],
    access: AccessStandard,
    turning_mm: int = 0,
    stack_point: tuple[int, int] | None = None,
    time_limit_s: float = 4.0,
    deterministic: bool = False,
) -> PackResult:
    """حزم طقم تجهيزات في غرفة بأبعاد معلومة (إحداثيات مطلقة بالمم)."""
    if not codes:
        return PackResult((), True)

    x, y, w, h = room_rect
    # الغرفة تُقلَّص إلى الشبكة: أدنى يُقرَّب بالزيادة وأعلى بالنقصان
    rx, ry = _up(x), _up(y)
    rx2, ry2 = _down(x + w), _down(y + h)
    rw, rh = rx2 - rx, ry2 - ry
    if rw <= 0 or rh <= 0:
        return PackResult(
            (), False,
            f"الغرفة {w}×{h} مم أصغر من خطوة الشبكة ({GRID} مم)",
        )

    m = cp_model.CpModel()
    swing_clear = (
        FIX.door_swing_clear_of_activity
        and access is not AccessStandard.M4_1
    )
    cands = _build(
        m, codes, rx, ry, rw, rh, door_zones, turning_mm, swing_clear
    )
    if stack_point is not None:
        _drain_objective(m, cands, codes, stack_point)

    from planforge.solver.determinism import Limits, apply_limits

    solver = cp_model.CpSolver()
    apply_limits(solver, Limits(
        deterministic=deterministic, time_limit_s=time_limit_s, workers=4
    ))
    if solver.solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        door_w = max((z[2] for z in door_zones), default=DEFAULT_DOOR_MM)
        need = minimal_envelope(
            codes, access, turning_mm, door_w, deterministic
        )
        detail = (
            f" (أصغر غرفة ممكنة ≈ {need.min_dim}×{need.max_dim} مم)"
            if need.ok else ""
        )
        return PackResult(
            (), False,
            f"لا يمكن حزم {', '.join(codes)} في {w}×{h} مم{detail}",
            minimum=need if need.ok else None,
        )

    out: list[Placement] = []
    for i, code in enumerate(codes):
        for c in cands[f"{code}{i}"]:
            if not solver.value(c.lit):
                continue
            out.append(Placement(
                code=code,
                x=solver.value(c.x) * GRID,
                y=solver.value(c.y) * GRID,
                w=c.bw * GRID,
                h=c.bh * GRID,
                rotation_deg=c.rot,
                activity=(
                    solver.value(c.ax) * GRID,
                    solver.value(c.ay) * GRID,
                    c.aw * GRID,
                    c.ah * GRID,
                ),
            ))
            break
    return PackResult(tuple(out), True)


@lru_cache(maxsize=256)
def minimal_envelope(
    codes: tuple[str, ...],
    access: AccessStandard,
    turning_mm: int = 0,
    door_width: int = DEFAULT_DOOR_MM,
    deterministic: bool = False,
) -> MinEnvelope:
    """
    أصغر غرفة تستوعب الطقم.

    هذا ما يُغذّي المُحلّل رجوعًا قبل التوليد؛ يُحلّ بتصغير المساحة على
    نفس نموذج الحزم، بباب افتراضي عند الزاوية ومربع دوران واحد إن
    اقتضى معيار الوصول. حين لا يوجد وضع معقول تُعاد قيمة صفرية.
    """
    if not codes:
        return MinEnvelope(0, 0, 0)

    m = cp_model.CpModel()
    rw = m.new_int_var(1, LIMIT, "rw")
    rh = m.new_int_var(1, LIMIT, "rh")
    swing_clear = (
        FIX.door_swing_clear_of_activity
        and access is not AccessStandard.M4_1
    )
    _build(
        m, codes, 0, 0, rw, rh,
        [(0, 0, door_width, door_width)], turning_mm, swing_clear,
    )
    area = m.new_int_var(1, LIMIT * LIMIT, "ra")
    m.add_multiplication_equality(area, [rw, rh])
    m.minimize(area * 4 + rw + rh)

    from planforge.solver.determinism import Limits, apply_limits

    solver = cp_model.CpSolver()
    apply_limits(solver, Limits(
        deterministic=deterministic, time_limit_s=8.0, workers=4
    ))
    if solver.solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return MinEnvelope(0, 0, 0)

    w = solver.value(rw) * GRID
    h = solver.value(rh) * GRID
    return MinEnvelope(min(w, h), max(w, h), w * h)
