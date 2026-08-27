"""
إعادة الإنتاج بين عمليتين منفصلتين.

الانحدار المحروس: `_jitter` كان مبنيًا على `hash()`، و`hash()` للنصوص
مُملَّح في بايثون فيتغيّر بين العمليات. النتيجة أن نفس المتطلب ونفس
البذرة يُخرجان تبليطين مختلفين في تشغيلين — فيُبطل `planforge replay`
وكل ادّعاء لإعادة الإنتاج.

الاختبار يشغّل عمليتين بـ`PYTHONHASHSEED` مختلفين. لا يمكن قياس هذا في
عملية واحدة: الملح يُثبَّت عند بدء المُفسِّر.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import pytest

PROBE = r"""
import json
from planforge.solver.storey import _jitter
out = {f"{r}|{v}": _jitter(r, v) for r in ("hall", "bed1", "kitchen")
       for v in (0, 1, 2)}
print(json.dumps(out, sort_keys=True))
"""


def _run(seed: str) -> dict:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True, text=True, env=env, timeout=120,
    )
    if proc.returncode != 0:
        pytest.fail(f"العملية فشلت (PYTHONHASHSEED={seed}): {proc.stderr}")
    return json.loads(proc.stdout)


def test_jitter_is_stable_across_processes():
    a = _run("0")
    b = _run("12345")
    assert a == b, (
        "تنويع الأوزان يتغيّر بين العمليات — عاد الاعتماد على hash()"
    )


def test_jitter_varies_by_variation():
    """
    الثبات ليس ثباتًا مطلقًا: التنويع يجب أن يغيّر الأوزان فعلًا، وإلا
    خرجت البدائل متطابقة.
    """
    values = _run("0")
    by_variation = {}
    for key, val in values.items():
        room, variation = key.split("|")
        by_variation.setdefault(room, {})[variation] = val
    assert any(
        len(set(v.values())) > 1 for v in by_variation.values()
    ), "التنويع لا يغيّر شيئًا"


def test_same_seed_same_tiling(brief, fast_cfg):
    """التبليط نفسه من نفس البذرة في العملية الواحدة."""
    from planforge.solver.generate import build_requests
    from planforge.solver.storey import solve_storey

    reqs = build_requests(brief)
    idx = sorted(reqs)[0]
    first = solve_storey(reqs[idx], fast_cfg, variation=0)
    second = solve_storey(reqs[idx], fast_cfg, variation=0)
    if first is None or second is None:
        pytest.skip("تعذّر الحل")
    assert first.signature() == second.signature()
    assert first.band_x == second.band_x


SOLVER_PROBE = r"""
import json
from planforge.model.brief import Brief
from planforge.solver.config import SolverConfig
from planforge.solver.generate import build_requests
from planforge.solver.storey import solve_storey

brief = Brief.model_validate(json.loads(%r))
cfg = SolverConfig(seed=7, time_limit_s=6.0, deterministic=True)
reqs = build_requests(brief)
idx = sorted(reqs)[0]
sol = solve_storey(reqs[idx], cfg, variation=0)
print(json.dumps(
    sorted((r, x.x, x.y, x.w, x.h) for r, x in sol.rects.items())
    if sol else []
))
"""


def _solve_in_process(brief_dict, seed: str) -> list:
    import json as _json
    env = {**os.environ, "PYTHONHASHSEED": seed}
    proc = subprocess.run(
        [sys.executable, "-c", SOLVER_PROBE % _json.dumps(brief_dict)],
        capture_output=True, text=True, env=env, timeout=300,
    )
    if proc.returncode != 0:
        pytest.fail(f"العملية فشلت: {proc.stderr}")
    return json.loads(proc.stdout)


@pytest.mark.slow
def test_deterministic_path_is_stable_across_processes(brief_dict):
    """
    الادّعاء المركزي: نفس المتطلب + نفس البذرة + المسار الحتمي ⟹ نفس
    التبليط في عمليتين منفصلتين.

    الانحدار المحروس أعمق من `_jitter`: CP-SAT بـ`num_workers > 1` أو
    بحدٍّ زمني بساعة الحائط يُعيد حلولًا مختلفة للنموذج نفسه، فيُبطل
    `planforge replay` بلا أن يكشف شيء ذلك.
    """
    a = _solve_in_process(brief_dict, "0")
    b = _solve_in_process(brief_dict, "9999")
    if not a:
        pytest.skip("تعذّر الحل في المسار الحتمي")
    assert a == b, "المسار الحتمي غير حتمي — راجع apply_limits"
