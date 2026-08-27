"""إعدادات المُحلّل. كل حقل هنا معامل محرك لا رقم كودي — لا يحتاج توقيعًا."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SolverConfig:
    grid_mm: int = 100
    """
    شبكة التبليط. أكبر = فضاء حل أضيق وحلّ أسرع، وتقريب أخشن للمساحات.
    الباقي دون الشبكة يُلحق بآخر حدّ، فيبقى التبليط تامًا.
    """

    time_limit_s: float = 20.0
    n_alternatives: int = 6
    seed: int = 0
    workers: int = 8

    max_bands_per_zone: int = 4
    """
    عدد الأشرطة الرأسية في كل منطقة. سعة الغرف غير الحركية =
    2 × هذا العدد. ارفعه إن أخرج `diagnose` الرمز BANDS-TOO-FEW.
    """

    min_band_mm: int = 1800
    """أضيق شريط. يحدّ أصغر مساحة ممكنة لأي غرفة: العرض × أقل ارتفاع."""

    min_spine_mm: int = 1000
    """أقل ارتفاع لشريط الحركة. مستهدف الردهة ÷ عرض المظروف يجب أن يبلغه."""

    deterministic: bool = False
    """
    المسار الحتمي: خيط واحد وحدٌّ بالزمن الحتمي.

    يلزم لكل ما يُدّعى فيه إعادة الإنتاج — `replay` والحالات المرجعية.
    الافتراض `False` لأن التوليد التفاعلي يُقايض الحتمية بالسرعة، وهذا
    مُعلَن لا مُخفى.
    """

    def with_(self, **changes) -> SolverConfig:
        from dataclasses import replace
        return replace(self, **changes)

    def limits(self, *, variation: int = 0) -> "Limits":
        from planforge.solver.determinism import Limits
        return Limits(
            deterministic=self.deterministic,
            time_limit_s=self.time_limit_s,
            workers=self.workers,
            seed=self.seed * 1000 + variation,
        )
