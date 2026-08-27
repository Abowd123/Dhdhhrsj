"""
تبليط دور واحد بـ CP-SAT.

البنية: شجرة قطع (guillotine) بعمق ثابت — وهذا قرار لا تفصيلة:

    المظروف
      ├── منطقة سفلى  → أشرطة رأسية → غرف مكدّسة أفقيًا
      ├── شريط الحركة → غرف متجاورة بعرض كامل (اختياري)
      └── منطقة عليا  → أشرطة رأسية → غرف مكدّسة أفقيًا

ثلاثة مكاسب من هذه البنية تحديدًا:
  • التبليط الكامل مضمون بنيويًا: مجموع العروض = العرض، ومجموع
    الارتفاعات في كل شريط = ارتفاع المنطقة. لا فراغ ولا تراكب بالبناء،
    لا بالفحص بعد الحدث.
  • حدود الأشرطة خطوط مستمرة على كل العمق ⇒ `structural_lines` تجد
    جدرانًا حاملة حقيقية، لا شظايا.
  • البنية شجرة قطع ⇒ شبكة خطوط المحرر تُشتق منها بلا لبس.

الثمن: مخططات لا تُمثَّل بشجرة قطع (غرفة على شكل L حول أخرى، فناء
داخلي) خارج فضاء الحل. مقبول لسكن صفّي؛ غير مقبول لمبنى معقّد.

الحركة تُنمذَج كشريط بعرض كامل لأن هذا ما يجعل كل غرفة تلامسه — وهو
شرط الاتصال الحقيقي، لا تفضيلًا شكليًا.

قيدٌ يلزم معرفته قبل كتابة أي متطلب: التبليط **تام**، فمجموع مساحات
غرف الدور يساوي مساحة المظروف ولا يقاربه. الفرق يظهر INFEASIBLE بلا
سبب مفهوم — و`planforge diagnose --fast` يقيسه في ملّي ثانية.
"""
from __future__ import annotations
import zlib
from dataclasses import dataclass, field
from ortools.sat.python import cp_model
from planforge.codes.uk.profile import UK
from planforge.enums import RoomType
from planforge.geometry.rect import Rect
from planforge.model.brief import RoomRequirement

SPINE_TYPES = frozenset({
    RoomType.ENTRANCE_HALL, RoomType.HALL, RoomType.LANDING, RoomType.LOBBY,
})

W_AREA = 100          # وزن انحراف المساحة عن المستهدف
W_ASPECT = 40         # وزن تجاوز النسبة الباعية
W_SPINE = 6           # وزن مساحة الحركة (تقليلها مطلوب لا مجانًا)

ABSOLUTE_FLOOR_MM = 700


@dataclass(frozen=True, slots=True)
class StoreyRequest:
    index: int
    envelope: Rect
    rooms: tuple[RoomRequirement, ...]
    protected_stair: bool = False
    require_spine: bool = True


@dataclass
class StoreySolution:
    index: int
    envelope: Rect
    rects: dict[str, Rect]
    band_x: tuple[int, ...]          # حدود الأشرطة (مطلقة، مم)
    spine: tuple[int, int] | None    # (y, h) لشريط الحركة إن وُجد
    objective: int
    variation: int
    types: dict[str, RoomType] = field(default_factory=dict)

    def with_types(self, types: dict[str, RoomType]) -> StoreySolution:
        self.types = dict(types)
        return self

    def signature(self) -> frozenset[tuple[str, int, int, int, int]]:
        return frozenset(
            (rid, r.x, r.y, r.w, r.h) for rid, r in self.rects.items()
        )


@dataclass
class _Cfg:
    """قراءة متحفّظة لإعدادات المُحلّل — أي حقل ناقص يأخذ افتراضًا معقولًا."""
    grid_mm: int = 100
    time_limit_s: float = 20.0
    seed: int = 0
    workers: int = 8
    max_bands: int = 4
    min_band_mm: int = 1800
    min_spine_mm: int = 1000
    deterministic: bool = False

    @classmethod
    def of(cls, cfg) -> _Cfg:
        def g(n, d):
            return getattr(cfg, n, d)
        return cls(
            grid_mm=g("grid_mm", 100),
            time_limit_s=g("time_limit_s", 20.0),
            seed=g("seed", 0),
            workers=g("workers", 8),
            max_bands=g("max_bands_per_zone", 4),
            min_band_mm=g("min_band_mm", 1800),
            min_spine_mm=g("min_spine_mm", 1000),
            deterministic=g("deterministic", False),
        )


def _jitter(room_id: str, variation: int) -> int:
    """
    تنويع طفيف في وزن كل غرفة، ثابت بين التشغيلات.

    `hash()` غير مناسب هنا: بايثون يُملّح تلبيد النصوص، فيتغيّر بين
    العمليات ويُبطل إعادة إنتاج المخطط من المتطلب والبذرة.
    """
    digest = zlib.crc32(f"{room_id}\x00{variation}".encode("utf-8"))
    return (digest % 7) - 3


def _room_floor(req: RoomRequirement) -> int:
    """أصغر بعد مسموح: العرف المهني أو ما نصّ عليه المتطلب، أيهما أكبر."""
    floor = UK.practical_min_width.get(req.type, ABSOLUTE_FLOOR_MM)
    return max(floor, getattr(req, "min_width_mm", None) or 0)


def _area_range(req: RoomRequirement) -> tuple[int, int]:
    lo = req.min_area_mm2 or int(req.target_area_mm2 * 0.85)
    hi = req.max_area_mm2 or int(req.target_area_mm2 * 1.45)
    return (min(lo, req.target_area_mm2), max(hi, req.target_area_mm2))


def _aspect_cap(req: RoomRequirement) -> float:
    return float(req.max_aspect or UK.max_aspect_default)


def _height_if(
    m: cp_model.CpModel, lit, h, hi: int, tag: str
) -> cp_model.IntVar:
    """h إن كانت الغرفة في هذا الشريط، وصفر خلاف ذلك."""
    v = m.new_int_var(0, hi, f"hif_{tag}")
    m.add(v == h).only_enforce_if(lit)
    m.add(v == 0).only_enforce_if(lit.negated())
    return v


def solve_storey(
    req: StoreyRequest, cfg, *, variation: int = 0
) -> StoreySolution | None:
    """
    يحل تبليط دور واحد.

    `variation` يغيّر بذرة المُحلّل وتوزيع الأوزان الطفيف، فتخرج بدائل
    مختلفة بنيويًا لا مجرد انعكاسات. يعود None عند التعذّر —
    `planforge diagnose` يقول لماذا.
    """
    c = _Cfg.of(cfg)
    G = c.grid_mm
    env = req.envelope
    W = env.w // G
    H = env.h // G
    if W < 2 or H < 2:
        return None

    rooms = list(req.rooms)
    if not rooms:
        return None

    # خرائط الإحداثيات: آخر حدٍّ يُلحَق به الباقي دون G، فيبقى التبليط تامًا
    mx = lambda vx: env.x2 if vx >= W else env.x + vx * G
    my = lambda vy: env.y2 if vy >= H else env.y + vy * G

    m = cp_model.CpModel()
    spine_ok = req.require_spine and any(r.type in SPINE_TYPES for r in rooms)

    # ─── المناطق وشريط الحركة ───
    zl = m.new_int_var(0, H, "zl")          # ارتفاع المنطقة السفلى
    hs = m.new_int_var(0, H, "hs")          # ارتفاع شريط الحركة
    zu = m.new_int_var(0, H, "zu")          # ارتفاع المنطقة العليا
    m.add(zl + hs + zu == H)

    spine_used = m.new_bool_var("spine_used")
    if spine_ok:
        m.add(spine_used == 1)              # الحركة إلزامية إن طُلبت
        m.add(hs >= -(-c.min_spine_mm // G))
    else:
        m.add(spine_used == 0)
        m.add(hs == 0)

    zone_h = (zl, zu)
    zone_on = [m.new_bool_var(f"zon{z}") for z in range(2)]
    for z in range(2):
        m.add(zone_h[z] == 0).only_enforce_if(zone_on[z].negated())
        m.add(zone_h[z] >= 1).only_enforce_if(zone_on[z])

    # ─── الأشرطة ───
    bw: list[list[cp_model.IntVar]] = []
    bon: list[list[cp_model.IntVar]] = []
    bx: list[list[cp_model.IntVar]] = []
    min_band = -(-c.min_band_mm // G)
    for z in range(2):
        wrow, orow, xrow = [], [], []
        for b in range(c.max_bands):
            w = m.new_int_var(0, W, f"bw{z}_{b}")
            on = m.new_bool_var(f"bon{z}_{b}")
            m.add(w == 0).only_enforce_if(on.negated())
            m.add(w >= min_band).only_enforce_if(on)
            if b:
                m.add_implication(on, orow[b - 1])   # كسر التناظر
            wrow.append(w)
            orow.append(on)
        m.add(sum(wrow) == W).only_enforce_if(zone_on[z])
        for b in range(c.max_bands):
            x = m.new_int_var(0, W, f"bx{z}_{b}")
            m.add(x == sum(wrow[:b]))
            xrow.append(x)
            m.add_implication(orow[b], zone_on[z])
        bw.append(wrow)
        bon.append(orow)
        bx.append(xrow)

    # ─── الغرف ───
    ids = [r.id for r in rooms]
    rw, rh, rx, ry, ra = {}, {}, {}, {}, {}
    terms: list[cp_model.LinearExpr] = []
    spine_slots: list[tuple[cp_model.IntervalVar, cp_model.IntVar]] = []
    band_slots: dict[tuple[int, int], list] = {
        (z, b): [] for z in range(2) for b in range(c.max_bands)
    }

    for rq in rooms:
        i = rq.id
        floor = -(-_room_floor(rq) // G)
        lo_a, hi_a = _area_range(rq)
        cap = int(_aspect_cap(rq) * 100)

        w = m.new_int_var(floor, W, f"w_{i}")
        h = m.new_int_var(floor, H, f"h_{i}")
        x = m.new_int_var(0, W, f"x_{i}")
        y = m.new_int_var(0, H, f"y_{i}")
        area = m.new_int_var(1, W * H, f"a_{i}")
        m.add_multiplication_equality(area, [w, h])
        m.add(area >= max(1, lo_a // (G * G)))
        m.add(area <= -(-hi_a // (G * G)))
        m.add(x + w <= W)
        m.add(y + h <= H)
        rw[i], rh[i], rx[i], ry[i], ra[i] = w, h, x, y, area

        # النسبة الباعية بمرونة مُعاقَبة لا بقيد صلب
        over = m.new_int_var(0, W + H, f"ov_{i}")
        m.add(w * 100 - h * cap <= over * cap)
        m.add(h * 100 - w * cap <= over * cap)
        terms.append(W_ASPECT * over)

        # انحراف المساحة عن المستهدف
        dev = m.new_int_var(0, W * H, f"dv_{i}")
        m.add_abs_equality(dev, area - rq.target_area_mm2 // (G * G))
        terms.append(max(1, W_AREA + _jitter(i, variation)) * dev)

        # المواضع الممكنة
        opts: list[cp_model.IntVar] = []
        if spine_ok and rq.type in SPINE_TYPES:
            s = m.new_bool_var(f"sp_{i}")
            opts.append(s)
            m.add(y == zl).only_enforce_if(s)
            m.add(h == hs).only_enforce_if(s)
            wsp = m.new_int_var(0, W, f"wsp_{i}")
            m.add(wsp == w).only_enforce_if(s)
            m.add(wsp == 0).only_enforce_if(s.negated())
            x2s = m.new_int_var(0, W, f"spx2_{i}")
            spine_slots.append((
                m.new_optional_interval_var(x, w, x2s, s, f"spx_{i}"), wsp
            ))
            terms.append(W_SPINE * area)

        for z in range(2):
            for b in range(c.max_bands):
                lb = m.new_bool_var(f"in_{i}_{z}_{b}")
                opts.append(lb)
                m.add_implication(lb, bon[z][b])
                m.add(w == bw[z][b]).only_enforce_if(lb)
                m.add(x == bx[z][b]).only_enforce_if(lb)
                if z == 0:
                    m.add(y + h <= zl).only_enforce_if(lb)
                else:
                    m.add(y >= zl + hs).only_enforce_if(lb)
                    m.add(y + h <= H).only_enforce_if(lb)
                y2 = m.new_int_var(0, H, f"y2_{i}_{z}_{b}")
                m.add(y2 == y + h)
                band_slots[(z, b)].append((
                    m.new_optional_interval_var(
                        y, h, y2, lb, f"iy_{i}_{z}_{b}"
                    ),
                    lb, h, f"{i}_{z}_{b}",
                ))
        m.add_exactly_one(opts)

    # ─── تجزيء تام: عدم تراكب + تغطية كاملة ───
    if spine_slots:
        m.add_no_overlap([iv for iv, _ in spine_slots])
        m.add(sum(wv for _, wv in spine_slots) == W).only_enforce_if(spine_used)
    for (z, b), entries in band_slots.items():
        if not entries:
            continue
        m.add_no_overlap([iv for iv, _, _, _ in entries])
        m.add(
            sum(
                _height_if(m, lit, hv, H, tag)
                for _, lit, hv, tag in entries
            ) == zone_h[z]
        ).only_enforce_if(bon[z][b])

    m.minimize(sum(terms))

    from planforge.solver.determinism import Limits, apply_limits

    solver = cp_model.CpSolver()
    apply_limits(solver, Limits(
        deterministic=c.deterministic,
        time_limit_s=c.time_limit_s,
        workers=c.workers,
        seed=c.seed * 1000 + variation,
    ))
    if not c.deterministic:
        solver.parameters.randomize_search = variation > 0
    if solver.solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    rects: dict[str, Rect] = {}
    for i in ids:
        x0, y0 = solver.value(rx[i]), solver.value(ry[i])
        x1 = x0 + solver.value(rw[i])
        y1 = y0 + solver.value(rh[i])
        rects[i] = Rect(mx(x0), my(y0), mx(x1) - mx(x0), my(y1) - my(y0))

    edges: set[int] = {env.x, env.x2}
    for z in range(2):
        for b in range(c.max_bands):
            if solver.value(bon[z][b]):
                edges.add(mx(solver.value(bx[z][b])))

    spine = None
    if spine_ok and solver.value(spine_used):
        y0 = solver.value(zl)
        spine = (my(y0), my(y0 + solver.value(hs)) - my(y0))

    return StoreySolution(
        index=req.index, envelope=env, rects=rects,
        band_x=tuple(sorted(edges)), spine=spine,
        objective=int(solver.objective_value), variation=variation,
    ).with_types({r.id: r.type for r in rooms})
