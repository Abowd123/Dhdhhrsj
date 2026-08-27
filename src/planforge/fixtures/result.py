"""
نتيجة التأثيث — منفصلة عن الحزم قصدًا.

`rules/fixture_rules.py` يقرأ هذه البنية، ولو عُرِّفت في `pack.py` لَجرّ
كل مُدقِّق CP-SAT معه. الفصل يجعل التدقيق قابلًا للاستيراد بلا `ortools`.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MinEnvelope:
    """أصغر غرفة تستوعب طقمًا: (أقل بعد، أكبر بعد، المساحة)."""
    min_dim: int
    max_dim: int
    area: int

    @property
    def ok(self) -> bool:
        return self.min_dim > 0 and self.area > 0


@dataclass(frozen=True, slots=True)
class KitchenAudit:
    room: str
    usable_run_mm: int
    required_run_mm: int
    gangway_mm: int
    required_gangway_mm: int
    sides: tuple[str, ...]
    problems: tuple[tuple[str, bool], ...] = ()
    """(الرسالة، هل هي خطأ؟) — الطول والمجاز أخطاء، والباقي تحذيرات."""

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def run_margin(self) -> float:
        if not self.required_run_mm:
            return 0.0
        return (
            (self.usable_run_mm - self.required_run_mm)
            / self.required_run_mm
        )


@dataclass
class FixtureOutcome:
    failures: list[str] = field(default_factory=list)
    unfurnishable: dict[str, MinEnvelope] = field(default_factory=dict)
    kitchens: dict[str, KitchenAudit] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    @classmethod
    def empty(cls) -> FixtureOutcome:
        """يُستخدم عند `--no-fixtures`: لا تأثيث ولا أحكام عليه."""
        return cls()
