"""
نواة محرك القواعد.

المبدأ الحاكم: القاعدة تُعرَّف مرة وتُستخدم مرتين — قيدًا يوجّه المُحلّل،
وفحصًا يوثّق النتيجة. أي قاعدة تُكتب في مكانين ستتباعد نسختاها.

`Rule.emits` ليس تفصيلة إدارية: `assurance.assess()` يقرأ
`ComplianceReport.rules_run` ليعرف على أي أرقام كود استند الحكم. لو
سجّلنا فيه اسم القاعدة بدل معرّفات مخالفاتها، خرجت شجرة الاستناد فارغة
وأعلنت بوابة التسليم جاهزيةً لم تُفحص.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Iterable


class Severity(StrEnum):
    ERROR = "error"   # مخالفة كود أو استحالة هندسية — المخطط مرفوض
    WARN = "warn"     # مقبول لكن دون العرف الجيد
    INFO = "info"     # ملاحظة معلوماتية


SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}


@dataclass(frozen=True, slots=True)
class Violation:
    rule_id: str
    severity: Severity
    message: str
    reference: str = ""       # الفقرة المُدّعاة — تُنسب لا تُصدَّق
    storey: int | None = None
    rooms: tuple[str, ...] = ()
    actual: str = ""
    required: str = ""

    def line(self) -> str:
        loc = f" [دور {self.storey}]" if self.storey is not None else ""
        rooms = f" ({', '.join(self.rooms)})" if self.rooms else ""
        detail = ""
        if self.actual or self.required:
            detail = f" | المقيس: {self.actual} — المطلوب: {self.required}"
        ref = f" | {self.reference}" if self.reference else ""
        return f"{self.rule_id}{loc}{rooms}: {self.message}{detail}{ref}"

    def key(self) -> tuple[str, str, tuple[str, ...]]:
        """هوية المخالفة — تُستخدم لمقارنة حالتين في المحرر."""
        return (self.rule_id, str(self.storey), self.rooms)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    title: str
    reference: str
    check: Callable[..., Iterable[Violation]]
    tags: frozenset[str] = frozenset()
    emits: tuple[str, ...] = ()
    """
    معرّفات المخالفات التي يمكن أن تُصدرها هذه القاعدة. تُلحق بـ
    `rules_run` فتصل إلى طبقة الاعتماد. إغفالها يُخفي أرقامًا غير موقَّعة.
    """


@dataclass
class ComplianceReport:
    project_name: str
    violations: list[Violation] = field(default_factory=list)
    rules_run: list[str] = field(default_factory=list)
    """
    معرّفات المخالفات التي **فُحصت**، لا التي وقعت. حكم «مطابق» يستند
    إلى الأرقام نفسها التي كان سيستند إليها لو خالف.
    """

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Violation]:
        return [v for v in self.violations if v.severity is Severity.WARN]

    @property
    def ok(self) -> bool:
        return not self.errors

    def sort(self) -> None:
        self.violations.sort(
            key=lambda v: (SEVERITY_ORDER[v.severity], v.rule_id,
                           v.storey if v.storey is not None else -1)
        )

    def summary(self) -> str:
        return (
            f"{self.project_name}: {len(self.rules_run)} فحصًا، "
            f"{len(self.errors)} خطأ، {len(self.warnings)} تحذيرًا"
        )
