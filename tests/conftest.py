"""تجهيزات مشتركة. المتطلبات صغيرة قصدًا: الاختبار يجب أن يعمل بسرعة."""
from __future__ import annotations
import pytest
from planforge.enums import AccessStandard, RoomType
from planforge.units import m2

BUNGALOW = {
    "project_name": "test-bungalow",
    "seed": 7,
    "bedspaces": 3,
    "plot": {"width_mm": 9000, "depth_mm": 11000},
    "setbacks": {
        "front_mm": 1000, "rear_mm": 1000,
        "left_mm": 500, "right_mm": 500,
    },
    "storeys": [
        {"index": 0, "floor_level_mm": 0, "floor_to_ceiling_mm": 2400},
    ],
    "access_standard": "M4(1)",
    "rooms": [
        {"id": "hall", "type": "entrance_hall",
         "target_area_mm2": m2(9.0), "storey": 0},
        {"id": "living", "type": "living",
         "target_area_mm2": m2(21.0), "storey": 0},
        {"id": "kitchen", "type": "kitchen",
         "target_area_mm2": m2(12.0), "storey": 0},
        {"id": "bed1", "type": "bedroom_main",
         "target_area_mm2": m2(14.0), "storey": 0},
        {"id": "bed2", "type": "bedroom_single",
         "target_area_mm2": m2(10.0), "storey": 0},
        {"id": "bath", "type": "bathroom",
         "target_area_mm2": m2(6.0), "storey": 0},
    ],
}
"""
مجموع المستهدفات 72.0 م² = مساحة المظروف (8.0 × 9.0) بالتمام.

`bedspaces = 3` يطابق أسرّة الغرف (مزدوجة + فردية) فلا يُصدر FEAS-007،
و`ndss_gia(3, 2, 1)` = 61 م² دون المساحة الصافية (66.99 م²) فيمرّ
NDSS-003 و DRW-005 معًا. هذه الأرقام محسوبة لا مُجرَّبة — عدّلها إن
غيّرتَ جدول NDSS.
"""


@pytest.fixture(scope="session")
def brief_dict() -> dict:
    return {**BUNGALOW}


@pytest.fixture(scope="session")
def brief(brief_dict):
    from planforge.model.brief import Brief
    return Brief.model_validate(brief_dict)


@pytest.fixture(scope="session")
def fast_cfg():
    from planforge.solver.config import SolverConfig
    return SolverConfig(
        seed=7, n_alternatives=2, time_limit_s=8.0, workers=2
    )


@pytest.fixture(scope="session")
def solved(brief, fast_cfg):
    """
    مخطط محلول مرة واحدة للجلسة كلها.

    يُتخطّى الاختبار المعتمد عليه إن تعذّر الحل بدل أن يفشل: الفشل هنا
    يعني تعذّرًا في المُحلّل، وهو ما يقيسه `test_pipeline` وحده.
    """
    from planforge.pipeline import closest, run
    best, feas, attempted = run(brief, fast_cfg, skip_fixtures=True)
    result = best or closest(attempted)
    if result is None:
        pytest.skip(f"تعذّر الحل: {len(feas.errors)} مانع جدوى")
    return result
