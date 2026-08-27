"""
جلسة تعديل: تُطبّق العمليات، تعيد الحل، تُدقّق، وترفض ما يُدخل مخالفة.

الرفض يُقارن بالحالة السابقة لا بالصفر: المهندس قد يفتح ملفًا فيه مشاكل
ويُصلحها تدريجيًا، فمنعه من كل تعديل حتى يصير الملف سليمًا يجعل المحرر
عديم الفائدة.

والمقارنة على **مفاتيح** المخالفات لا على عددها: تعديلٌ ينقل مخالفة من
غرفة إلى أخرى يُرفض، لأن المشكلة لم تُحلّ بل انتقلت.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from planforge.drawing.build import build_drawing
from planforge.drawing.model import Drawing, PlacedOpening, WallRun
from planforge.enums import RoomType
from planforge.fixtures.result import FixtureOutcome
from planforge.geometry.lines import Topology, build_topology
from planforge.geometry.rect import Rect
from planforge.model.brief import Brief
from planforge.model.layout import Layout, RectModel
from planforge.ranking import Features, RankWeights, extract, score
from planforge.rules.core import ComplianceReport, Violation
from planforge.rules.drawing_rules import check_drawing
from planforge.rules.fixture_rules import check_fixtures
from planforge.rules.registry import default_registry
from planforge.solver.refine import assign_storage
from planforge.edit.ops import (
    FlipOpening, MoveOpening, MoveWall, Operation, ResizeRoom,
    SetOpeningWidth, SetRoomType, SwapRooms,
)
from planforge.edit.solve import RoomBounds, bounds_from_brief, resolve

MAX_HISTORY = 200


@dataclass
class State:
    layout: Layout
    drawing: Drawing
    layout_report: ComplianceReport
    drawing_report: ComplianceReport
    fixture_report: ComplianceReport
    fixtures: FixtureOutcome
    features: Features
    rank: float
    hints: dict[str, float] = field(default_factory=dict)

    @property
    def reports(self) -> tuple[ComplianceReport, ...]:
        return (
            self.layout_report, self.drawing_report, self.fixture_report
        )

    @property
    def errors(self) -> list[Violation]:
        return [v for rep in self.reports for v in rep.errors]

    @property
    def error_keys(self) -> set[tuple[str, str, tuple[str, ...]]]:
        return {v.key() for v in self.errors}

    @property
    def warnings_count(self) -> int:
        return sum(len(rep.warnings) for rep in self.reports)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class EditResult:
    ok: bool
    message: str = ""
    introduced: list[Violation] = field(default_factory=list)
    moved_lines: dict[str, int] = field(default_factory=dict)


class EditSession:
    """
    جلسة على مشروع واحد.

    الطوبولوجيا تُعاد بناؤها بعد كل عملية ناجحة: تحريك الجدران قد يجعل
    خطين متجاورين يتلامسان أو يتفارقان، فتتغيّر الخطوط نفسها لا مواضعها
    فقط.
    """

    def __init__(
        self,
        brief: Brief,
        layout: Layout,
        *,
        arabic_labels: bool = True,
        weights: RankWeights | None = None,
        skip_fixtures: bool = False,
        hints: dict[str, float] | None = None,
        deterministic: bool = False,
    ) -> None:
        self.brief = brief
        self.arabic = arabic_labels
        self.weights = weights or RankWeights()
        self.skip_fixtures = skip_fixtures
        self.deterministic = deterministic
        self.history: list[dict] = []
        self._undo: list[tuple[State, dict]] = []
        self._redo: list[tuple[State, dict]] = []
        self.state = self.evaluate(layout, hints or {})
        self.topo: dict[int, Topology] = self._build_topologies(layout)

    # ─────────── سجل التعديلات ───────────

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def depth(self) -> int:
        return len(self.history)

    # ─────────── بناء وتقييم ───────────

    def _build_topologies(self, layout: Layout) -> dict[int, Topology]:
        return {
            st.index: build_topology(
                st.index, st.envelope.to_rect(),
                {r.id: r.r for r in st.rooms},
            )
            for st in layout.storeys
        }

    def evaluate(self, layout: Layout, hints: dict[str, float]) -> State:
        """
        الأنبوب الكامل على حالة واحدة: تخزين ← جدران ← تجهيزات ← تدقيق.

        واجهة عامة لا خاصة: `Project` يستدعيها عند فتح ملف محفوظ، فبقاؤها
        خاصةً كان يجبره على كسر التغليف.

        `assign_storage` يُستدعى في كل تقييم لا مرة واحدة: تغيير حجم غرفة
        نوم يبطل نصيبها من تخزين NDSS §9، وحمله من حالة سابقة يُنتج رقمًا
        لا يطابق الهندسة الحالية.
        """
        assign_storage(layout.storeys, self.brief)

        dwg, problems = build_drawing(
            layout, self.brief,
            arabic_labels=self.arabic, opening_hints=hints,
        )
        lrep = default_registry().run(layout, self.brief)
        drep = check_drawing(dwg, self.brief, problems)

        if self.skip_fixtures:
            fout = FixtureOutcome.empty()
        else:
            from planforge.fixtures.build import furnish
            fout = furnish(dwg, self.brief, deterministic=self.deterministic)
        frep = check_fixtures(dwg, self.brief, fout)

        feats = extract(dwg, self.brief, lrep, drep, frep, fout.kitchens)
        return State(
            layout=layout, drawing=dwg,
            layout_report=lrep, drawing_report=drep, fixture_report=frep,
            fixtures=fout, features=feats,
            rank=score(feats, self.weights), hints=dict(hints),
        )

    def _layout_with(
        self,
        storey: int,
        rects: dict[str, Rect],
        types: dict[str, RoomType] | None = None,
    ) -> Layout:
        new = self.state.layout.model_copy(deep=True)
        for st in new.storeys:
            if st.index != storey:
                continue
            for r in st.rooms:
                if r.id in rects:
                    r.rect = RectModel.of(rects[r.id])
                if types and r.id in types:
                    r.type = types[r.id]
        return new

    def _bounds(
        self, storey: int, override: dict[str, RoomType] | None = None
    ) -> dict[str, RoomBounds]:
        types = {
            r.id: r.type for r in self.state.layout.storey(storey).rooms
        }
        if override:
            types.update(override)
        return bounds_from_brief(self.brief, types)

    # ─────────── التطبيق ───────────

    def apply(self, op: Operation) -> EditResult:
        try:
            candidate, hints, moved, reason = self._compute(op)
        except (KeyError, ValueError) as exc:
            return EditResult(False, str(exc))
        if candidate is None:
            return EditResult(False, reason or "تعذّر إعادة الحل")

        before = self.state.error_keys
        new_state = self.evaluate(candidate, hints)
        introduced = [
            v for v in new_state.errors if v.key() not in before
        ]
        if introduced:
            return EditResult(
                False,
                f"التعديل مرفوض: يُدخل {len(introduced)} مخالفة جديدة",
                introduced,
            )

        payload = op.model_dump()
        self._undo.append((self.state, payload))
        if len(self._undo) > MAX_HISTORY:
            self._undo.pop(0)
        self._redo.clear()
        self.state = new_state
        self.topo = self._build_topologies(candidate)
        self.history.append(payload)

        fixed = len(before - new_state.error_keys)
        bits = [f"{len(moved)} خطًا تحرّك"] if moved else ["تم"]
        if fixed:
            bits.append(f"أُصلحت {fixed} مخالفة")
        return EditResult(True, "، ".join(bits), [], moved)

    def _compute(
        self, op: Operation
    ) -> tuple[Layout | None, dict[str, float], dict[str, int], str]:
        hints = dict(self.state.hints)

        if isinstance(op, MoveWall):
            topo = self._topo(op.storey)
            line = topo.line(op.line)
            if line.is_boundary:
                raise ValueError(
                    f"{op.line} جدار محيط — عدّل الارتدادات في المتطلب "
                    f"بدلًا منه"
                )
            res = resolve(
                topo, self._bounds(op.storey),
                pinned={op.line: op.coord_mm},
                deterministic=self.deterministic,
            )
            if not res.ok:
                return None, hints, {}, res.reason
            return (
                self._layout_with(op.storey, res.rects),
                hints, res.moved, "",
            )

        if isinstance(op, ResizeRoom):
            topo = self._topo(op.storey)
            if op.room not in topo.rooms:
                raise KeyError(
                    f"لا توجد غرفة {op.room} في الدور {op.storey}"
                )
            res = resolve(
                topo, self._bounds(op.storey),
                area_targets={op.room: op.target_area_mm2},
                deterministic=self.deterministic,
            )
            if not res.ok:
                return None, hints, {}, res.reason
            return (
                self._layout_with(op.storey, res.rects),
                hints, res.moved, "",
            )

        if isinstance(op, SetRoomType):
            try:
                rtype = RoomType(op.room_type)
            except ValueError as exc:
                raise ValueError(
                    f"نوع غرفة غير معروف: {op.room_type}"
                ) from exc
            topo = self._topo(op.storey)
            if op.room not in topo.rooms:
                raise KeyError(
                    f"لا توجد غرفة {op.room} في الدور {op.storey}"
                )
            res = resolve(
                topo, self._bounds(op.storey, {op.room: rtype}),
                deterministic=self.deterministic,
            )
            if not res.ok:
                return None, hints, {}, res.reason
            return (
                self._layout_with(op.storey, res.rects, {op.room: rtype}),
                hints, res.moved, "",
            )

        if isinstance(op, SwapRooms):
            st = self.state.layout.storey(op.storey)
            by_id = {r.id: r for r in st.rooms}
            if op.a not in by_id or op.b not in by_id:
                raise KeyError("إحدى الغرفتين غير موجودة في هذا الدور")
            swapped = {op.a: by_id[op.b].r, op.b: by_id[op.a].r}
            interim = self._layout_with(op.storey, swapped)
            try:
                topo = build_topology(
                    op.storey, st.envelope.to_rect(),
                    {r.id: r.r for r in interim.storey(op.storey).rooms},
                )
            except ValueError as exc:
                return None, hints, {}, (
                    f"التبادل يكسر التبليط ({exc}) — "
                    f"البصمتان مختلفتان جدًا"
                )
            res = resolve(
                topo, self._bounds(op.storey),
                deterministic=self.deterministic,
            )
            if not res.ok:
                return None, hints, {}, res.reason
            return (
                self._layout_with(op.storey, res.rects),
                hints, res.moved, "",
            )

        if isinstance(op, MoveOpening):
            placed = self._placed(op.storey, op.opening)
            run = self._run_of(op.storey, placed)
            span = max(1, run.length - placed.clear_width_mm)
            ratio = (op.position_mm - run.lo) / span
            hints[op.opening] = min(1.0, max(0.0, ratio))
            return (
                self.state.layout.model_copy(deep=True), hints, {}, "",
            )

        if isinstance(op, FlipOpening):
            self._placed(op.storey, op.opening)      # يتحقّق من الوجود
            hints[op.opening] = 1.0 - hints.get(op.opening, 0.5)
            return (
                self.state.layout.model_copy(deep=True), hints, {}, "",
            )

        if isinstance(op, SetOpeningWidth):
            layout = self.state.layout.model_copy(deep=True)
            found = False
            for st in layout.storeys:
                for o in st.openings:
                    if o.id == op.opening:
                        o.clear_width_mm = op.clear_width_mm
                        found = True
            if not found:
                raise KeyError(f"لا توجد فتحة {op.opening}")
            return layout, hints, {}, ""

        raise ValueError(f"عملية غير مُنفَّذة: {type(op).__name__}")

    def _topo(self, storey: int) -> Topology:
        topo = self.topo.get(storey)
        if topo is None:
            raise KeyError(f"لا يوجد دور {storey}")
        return topo

    def _placed(self, storey: int, oid: str) -> PlacedOpening:
        try:
            return self.state.drawing.storey(storey).opening(oid)
        except KeyError as exc:
            raise KeyError(
                f"لا توجد فتحة {oid} في الدور {storey}"
            ) from exc

    def _run_of(self, storey: int, placed: PlacedOpening) -> WallRun:
        run = self.state.drawing.storey(storey).run_carrying(placed)
        if run is None:
            raise ValueError(f"الفتحة {placed.id} ليست على أي جدار")
        return run

    # ─────────── التراجع ───────────

    def undo(self) -> EditResult:
        """
        الثبات المحفوظ: `history` تساوي دائمًا تتابع العمليات المؤدّي إلى
        `state`. كسرُه يُبطل `replay`.
        """
        if not self._undo:
            return EditResult(False, "لا يوجد ما يُتراجع عنه")
        previous, payload = self._undo.pop()
        self._redo.append((self.state, payload))
        self.state = previous
        self.topo = self._build_topologies(previous.layout)
        if self.history:
            self.history.pop()
        return EditResult(True, "تم التراجع")

    def redo(self) -> EditResult:
        if not self._redo:
            return EditResult(False, "لا يوجد ما يُعاد")
        restored, payload = self._redo.pop()
        self._undo.append((self.state, payload))
        self.state = restored
        self.topo = self._build_topologies(restored.layout)
        self.history.append(payload)
        return EditResult(True, "تمت الإعادة")
