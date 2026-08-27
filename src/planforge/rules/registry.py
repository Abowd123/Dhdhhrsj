"""سجل القواعد: مصدر الحقيقة الواحد."""
from __future__ import annotations
from planforge.model.brief import Brief
from planforge.model.layout import Layout
from planforge.rules.core import ComplianceReport, Rule


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def add(self, rule: Rule) -> None:
        if rule.id in self._rules:
            raise ValueError(f"قاعدة مكررة: {rule.id}")
        self._rules[rule.id] = rule

    def extend(self, rules: list[Rule]) -> None:
        for r in rules:
            self.add(r)

    def select(self, tags: set[str] | None = None) -> list[Rule]:
        if not tags:
            return list(self._rules.values())
        return [r for r in self._rules.values() if r.tags & tags]

    def emitted_codes(self) -> frozenset[str]:
        """كل معرّفات المخالفات المُعلنة — يفحصها اختبار خريطة الاستناد."""
        return frozenset(c for r in self._rules.values() for c in r.emits)

    @property
    def rules(self) -> list[Rule]:
        """للاختبارات والتشخيص. `emitted_codes()` أخصر لجمع المعرّفات."""
        return list(self._rules.values())

    def run(
        self, layout: Layout, brief: Brief, tags: set[str] | None = None
    ) -> ComplianceReport:
        report = ComplianceReport(project_name=layout.project_name)
        for rule in self.select(tags):
            report.rules_run.extend(rule.emits)
            report.violations.extend(rule.check(layout, brief))
        report.sort()
        return report


def default_registry() -> RuleRegistry:
    from planforge.codes.culture.majlis import MAJLIS_RULES
    from planforge.codes.uk.rules import UK_RULES
    from planforge.rules.geometric import GEOMETRIC_RULES

    reg = RuleRegistry()
    reg.extend(GEOMETRIC_RULES)
    reg.extend(UK_RULES)
    reg.extend(MAJLIS_RULES)
    return reg
