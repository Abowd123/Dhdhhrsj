"""
ملف المشروع: متطلب + مخطط + سجل التعديلات.

إعادة الإنتاج مضمونة بأربعة: المتطلب، والبذرة، وإصدار المحرك، وكل عملية
بالترتيب. `replay()` يتحقّق منها فعلًا — ويكشف أي تعديل صار مستحيلًا بعد
تغيّر إصدار المحرك أو تصحيح رقم كودي.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from planforge.edit.ops import parse_op
from planforge.edit.session import EditSession
from planforge.model.brief import Brief
from planforge.model.layout import Layout

PROJECT_VERSION = "1"
SUFFIX = ".pfproj.json"


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_version: str = PROJECT_VERSION
    engine_version: str
    deterministic: bool = False
    """
    هل وُلِّد المخطط الأصلي بالمسار الحتمي؟

    `False` يعني أن `replay` **قد** يُنتج حالة مختلفة: CP-SAT بأكثر من
    خيط وبحدٍّ زمني يُعيد حلولًا مختلفة للنموذج نفسه. لا يمكن إصلاح ذلك
    بأثر رجعي، فيُعلَن.
    """
    created: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    modified: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    brief: Brief
    layout: Layout
    """
    المخطط **الأصلي** كما وُلِّد. لا يتغيّر بالتعديلات — وهذا شرط
    `replay`: بلا نقطة بداية ثابتة لا معنى لإعادة تشغيل السجل.
    """
    history: list[dict] = []
    opening_hints: dict[str, float] = {}

    @classmethod
    def from_session(cls, s: EditSession, *, origin: Layout) -> Project:
        return cls(
            engine_version=origin.engine_version,
            deterministic=s.deterministic,
            brief=s.brief,
            layout=origin,
            history=list(s.history),
            opening_hints=dict(s.state.hints),
        )

    @classmethod
    def snapshot(cls, s: EditSession) -> Project:
        """
        حفظ الحالة الراهنة كنقطة بداية جديدة.

        يُفقد السجل قصدًا: من حفظ حالةً بعد عشرين تعديلًا لا يريد إعادة
        تشغيلها، بل البناء عليها. ومن يريد السجل يستخدم `from_session`.
        """
        return cls(
            engine_version=s.state.layout.engine_version,
            deterministic=s.deterministic,
            brief=s.brief,
            layout=s.state.layout,
            history=[],
            opening_hints=dict(s.state.hints),
        )

    def save(self, path: Path) -> Path:
        if not path.name.endswith(SUFFIX):
            path = path.with_name(path.stem + SUFFIX)
        self.modified = datetime.now(timezone.utc).isoformat()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.model_dump_json(indent=2), encoding="utf-8"
        )
        return path

    @classmethod
    def load(cls, path: Path) -> Project:
        obj = cls.model_validate_json(path.read_text(encoding="utf-8"))
        if obj.project_version != PROJECT_VERSION:
            raise ValueError(
                f"إصدار ملف مشروع غير مدعوم: {obj.project_version} "
                f"(المدعوم {PROJECT_VERSION})"
            )
        return obj

    def open_session(self, **kw) -> EditSession:
        """
        فتح جلسة على الحالة المحفوظة بلا إعادة تشغيل السجل.

        سريع، ويكفي للعمل اليومي. لكنه لا يتحقّق من قابلية إعادة الإنتاج
        — `replay()` هو ما يفعل ذلك.
        """
        session = EditSession(
            self.brief, self.layout,
            hints=dict(self.opening_hints),
            deterministic=self.deterministic, **kw,
        )
        session.history = list(self.history)
        return session

    def replay(self, **kw) -> tuple[EditSession, list[str]]:
        """
        إعادة تشغيل السجل من المخطط الأصلي.

        يتحقّق أن الملف قابل لإعادة الإنتاج، ويكشف التعديل الذي صار
        مستحيلًا: تصحيحُ رقم كودي قد يجعل تعديلًا كان مقبولًا يُدخل
        مخالفة اليوم — وهذا ما نريد أن نعرفه قبل التسليم لا بعده.
        """
        warnings: list[str] = []
        if not self.deterministic:
            warnings.append(
                "المخطط الأصلي وُلِّد بالمسار السريع غير الحتمي — إعادة "
                "التشغيل قد تُنتج حالة مختلفة. أعِد التوليد بـ--deterministic "
                "إن كانت إعادة الإنتاج مطلوبة."
            )
        session = EditSession(
            self.brief, self.layout, deterministic=True, **kw
        )
        failures: list[str] = []
        for i, raw in enumerate(self.history, start=1):
            try:
                res = session.apply(parse_op(raw))
            except (KeyError, ValueError) as exc:
                failures.append(f"[{i}] {raw.get('kind')}: {exc}")
                continue
            if not res.ok:
                failures.append(
                    f"[{i}] {raw.get('kind')}: {res.message}"
                )
        for oid, ratio in self.opening_hints.items():
            session.state.hints.setdefault(oid, ratio)
        return session, warnings + failures
