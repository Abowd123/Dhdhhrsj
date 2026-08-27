"""
حدود المُحلّل: مسار حتمي ومسار سريع.

CP-SAT غير حتمي لسببين، وكلٌّ منهما كافٍ وحده:

  • `num_workers > 1` — خيوط متسابقة، فأول حل بنفس القيمة يفوز، وأيُّها
    يسبق يعتمد على جدولة نظام التشغيل.
  • `max_time_in_seconds` — الحدّ بساعة الحائط يقطع البحث عند نقطة تتغيّر
    بحِمل الجهاز، فيُعاد حلٌّ مختلف على الجهاز نفسه.

فالحتمية تقتضي إبطالهما معًا: خيط واحد، وحدٌّ بالزمن **الحتمي** — وحدة
عمل مجرّدة يحسبها المُحلّل من عدد العُقد والانتشارات، لا ثوانٍ.

هذا يصحّح ادّعاءً كان قائمًا في المشروع: `test_reproducibility` يحرس
`_jitter` وحده، وقد أُصلح فعلًا بـ`zlib.crc32`. لكن مصدر عدم الحتمية
الحقيقي هو المُحلّل نفسه، فكان `planforge replay` يُعيد مخططًا مختلفًا
عن المحفوظ بلا أن يكشف الاختبار شيئًا.

الثمن معلوم: المسار الحتمي أبطأ 3–6× على المخططات المتوسطة. فالافتراض
سريع، و`replay` والاختبارات المرجعية تفرض الحتمي.
"""
from __future__ import annotations
from dataclasses import dataclass
from ortools.sat.python import cp_model

DET_UNITS_PER_SECOND = 6.0
"""
معامل تقريبي لتحويل ثوانٍ إلى وحدات زمن حتمي. ليس دقيقًا ولا يُمكن أن
يكون — الوحدة مجرّدة بحكم تعريفها. غرضه أن يبقى `time_limit_s` معنى
واحدًا في الواجهة بدل معاملَين يخطئ المستخدم بينهما.
"""


@dataclass(frozen=True, slots=True)
class Limits:
    deterministic: bool = False
    time_limit_s: float = 20.0
    workers: int = 8
    seed: int = 0

    @property
    def det_units(self) -> float:
        return max(1.0, self.time_limit_s * DET_UNITS_PER_SECOND)

    def describe(self) -> str:
        if self.deterministic:
            return f"حتمي (خيط واحد، {self.det_units:.0f} وحدة عمل)"
        return f"سريع ({self.workers} خيطًا، {self.time_limit_s:.0f} ث)"


def apply_limits(solver: cp_model.CpSolver, limits: Limits) -> None:
    """
    يضبط معاملات المُحلّل. المدخل الوحيد لكل مواضع الحل الأربعة.

    في المسار الحتمي لا يُضبط `max_time_in_seconds` إطلاقًا: ضبطُ الحدّين
    معًا يعني أن أيّهما سبق يقطع البحث — فيعود عدم الحتمية من الباب الذي
    أُغلق. المقايضة الصريحة: نموذج شاذّ قد يستمر أطول مما تتوقّع، ولا
    يوجد سقف زمني يحميك. هذا مقبول في `replay` واختبار مرجعي، وغير مقبول
    في خادم تفاعلي.
    """
    solver.parameters.random_seed = limits.seed
    if limits.deterministic:
        solver.parameters.num_workers = 1
        solver.parameters.max_deterministic_time = limits.det_units
        solver.parameters.randomize_search = False
        return
    solver.parameters.num_workers = limits.workers
    solver.parameters.max_time_in_seconds = limits.time_limit_s
