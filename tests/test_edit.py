"""المحرر: يحفظ التبليط، ويرفض ما يُدخل مخالفة، ويتراجع."""
from __future__ import annotations
import pytest
from planforge.edit.ops import MoveWall, ResizeRoom, parse_op
from planforge.edit.session import EditSession


@pytest.fixture
def session(brief, solved):
    return EditSession(brief, solved.layout, skip_fixtures=True)


def _movable(session):
    for storey, topo in session.topo.items():
        lines = topo.movable_lines()
        if lines:
            return storey, lines[0]
    pytest.skip("لا خط قابل للتحريك")


def test_boundary_wall_is_refused(session):
    storey, topo = 0, session.topo[0]
    boundary = next(
        l for l in topo.lines.values() if l.is_boundary
    )
    res = session.apply(
        MoveWall(storey=storey, line=boundary.id, coord_mm=100)
    )
    assert not res.ok
    assert "محيط" in res.message


def test_small_move_preserves_tiling(session):
    storey, line = _movable(session)
    res = session.apply(
        MoveWall(storey=storey, line=line.id, coord_mm=line.coord + 100)
    )
    if not res.ok:
        pytest.skip(f"الحل تعذّر عند هذا الموضع: {res.message}")
    st = session.state.layout.storey(storey)
    env = st.envelope.to_rect()
    total = sum(r.r.area for r in st.rooms)
    assert total == env.area, "التبليط لم يبقَ تامًا"


def test_absurd_move_is_refused(session):
    """موضع مستحيل يُرفض برسالة، لا باستثناء ولا بمخطط مكسور."""
    storey, line = _movable(session)
    res = session.apply(
        MoveWall(storey=storey, line=line.id, coord_mm=10)
    )
    assert not res.ok
    assert res.message


def test_undo_restores_previous_state(session):
    storey, line = _movable(session)
    before = session.state.layout.model_dump_json()
    res = session.apply(
        MoveWall(storey=storey, line=line.id, coord_mm=line.coord + 100)
    )
    if not res.ok:
        pytest.skip("لم يُطبَّق أي تعديل")
    assert session.can_undo
    assert session.state.layout.model_dump_json() != before
    session.undo()
    assert session.state.layout.model_dump_json() == before
    assert session.can_redo
    assert session.depth == 0


def test_undo_then_redo_keeps_history_intact(session):
    """
    `history` تساوي تتابع العمليات المؤدّي إلى `state`.

    الانحدار المحروس: `undo` كان ينزع العملية و`redo` لا يُعيدها، فيُحفَظ
    مشروع سجلّه أقصر من حالته ⇒ `replay` يُنتج مخططًا مختلفًا.
    """
    storey, line = _movable(session)
    res = session.apply(
        MoveWall(storey=storey, line=line.id, coord_mm=line.coord + 100)
    )
    if not res.ok:
        pytest.skip(f"لم يُطبَّق أي تعديل: {res.message}")

    after = session.state.layout.model_dump_json()
    assert session.depth == 1

    session.undo()
    assert session.depth == 0

    assert session.redo().ok
    assert session.depth == 1, "العملية لم تعد إلى السجل"
    assert session.state.layout.model_dump_json() == after


def test_storage_is_recomputed_on_resize(session, brief):
    """
    تكبير غرفة نوم يُعيد توزيع تخزين NDSS §9.

    الانحدار المحروس: النصيب كان يُحمَل من الحالة السابقة، فيتجاوز سقف
    النسبة عند التصغير أو يبقى دون الحق عند التكبير.
    """
    bed = next(
        (
            r for r in session.state.layout.storey(0).rooms
            if "bed" in r.id
        ),
        None,
    )
    if bed is None:
        pytest.skip("لا غرفة نوم")
    res = session.apply(
        ResizeRoom(
            storey=0, room=bed.id,
            target_area_mm2=int(bed.r.area * 1.10),
        )
    )
    if not res.ok:
        pytest.skip(f"التعديل مرفوض: {res.message}")
    updated = next(
        r for r in session.state.layout.storey(0).rooms if r.id == bed.id
    )
    cap = int(updated.r.area * 0.10)
    assert updated.storage_area_mm2 <= cap + 1, (
        "نصيب التخزين تجاوز سقف النسبة — لم يُعَد الحساب"
    )


def test_rejection_lists_the_violations(session):
    """
    الرفض يُعلن ما كان سيُدخله.

    رفضٌ بلا سبب يُفقد المهندس السيطرة، فيتجاوز المحرر ويعدّل بيده.
    """
    storey, line = _movable(session)
    res = session.apply(
        MoveWall(storey=storey, line=line.id, coord_mm=line.coord + 20)
    )
    if res.ok or not res.introduced:
        pytest.skip("هذا التعديل لم يُدخل مخالفة")
    assert all(v.rule_id for v in res.introduced)


def test_op_parsing_rejects_unknown():
    with pytest.raises(ValueError, match="غير معروفة"):
        parse_op({"kind": "demolish_everything"})


def test_project_roundtrip_and_replay(brief, solved, tmp_path):
    from planforge.project import Project

    session = EditSession(brief, solved.layout, skip_fixtures=True)
    storey, line = _movable(session)
    session.apply(
        MoveWall(storey=storey, line=line.id, coord_mm=line.coord + 100)
    )
    proj = Project.from_session(session, origin=solved.layout)
    path = proj.save(tmp_path / "p.pfproj.json")

    again = Project.load(path)
    assert again.brief.project_name == brief.project_name
    replayed, failures = again.replay(skip_fixtures=True)
    assert not failures, failures
    assert replayed.state.layout.model_dump_json() == \
        session.state.layout.model_dump_json(), (
            "إعادة التشغيل لم تُنتج الحالة نفسها"
        )
