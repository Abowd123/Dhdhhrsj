"""
ورقة عمل المراجعة: تخرج CSV، وتعود موقَّعة.

المشكلة التي تحلّها: توقيع نحو 250 رقمًا بأمر لكل رقم عملية لا تُكمَل،
فتبقى الأرقام غير موقَّعة وتصير بوابة التسليم عقبةً تُتجاوَز لا ضمانةً
تُحترم — وهذا أسوأ من ألا تكون موجودة.

المسار: تصدير مفلتر بالوثيقة (فتجلس مع PDF واحد) ومرتَّب بالخطر ← تملأ
عمودين ← استيراد يوقّع السليم بالجملة.

الثبات المحفوظ: الصفّ المحكوم عليه بالخطأ **لا يُوقَّع**. يُخرج في ملف
تصحيحات، فتُصحّح ملف الكود، ثم تُصدّر وتوقّع من جديد. لا توقيع على قيمة
مؤجّلة التصحيح.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from planforge.codes.provenance import (
    REGISTRY, Confidence, SafetyDirection, value_digest, values_of,
)
from planforge.codes.signing import (
    STATE_NOT_REQUIRED, STATE_SIGNED, SignatureBook, default_profiles,
)
from planforge.codes.usage import rules_using

ENCODING = "utf-8-sig"      # يجعل Excel يقرأ العربية بلا خطوات إضافية

READ_ONLY = (
    "path", "current_value", "unit", "confidence", "error_direction",
    "claimed_document", "claimed_edition", "claimed_clause",
    "engine_note", "used_by_rules", "state_now", "value_digest",
)
EDITABLE = (
    "verdict", "correct_value", "clause_confirmed", "reviewer", "review_note",
)
HEADER = (*READ_ONLY, *EDITABLE)

VERDICT_OK = frozenset({"ok", "correct", "صحيح", "سليم"})
VERDICT_WRONG = frozenset({"wrong", "incorrect", "خطأ", "خاطئ"})
VERDICT_SKIP = frozenset({"", "-", "skip", "later", "لاحقًا", "مؤجل"})


def _risk_key(path: str, state: str) -> tuple:
    """الأخطر أولًا: غير موقَّع، خطؤه تسامحي، من الذاكرة، يُستخدم كثيرًا."""
    prov = REGISTRY.get(path)
    return (
        state in (STATE_SIGNED, STATE_NOT_REQUIRED),
        not (prov and prov.safety_direction is SafetyDirection.PERMISSIVE),
        not (prov and prov.confidence is Confidence.RECALLED),
        -len(rules_using(path)),
        path,
    )


# ═══════════════ التصدير ═══════════════

def export_worksheet(
    path_out: Path,
    *,
    book: SignatureBook | None = None,
    document: str | None = None,
    confidence: str | None = None,
    include_signed: bool = False,
    limit: int | None = None,
) -> tuple[Path, int]:
    """
    يكتب ورقة عمل.

    `document` يفلتر بجزء من اسم الوثيقة المُدّعاة، فتُراجع وثيقةً واحدة
    في جلسة واحدة — وهذا ما يجعل المراجعة تُنجَز فعلًا بدل أن تُهجَر.
    """
    profiles = default_profiles()
    values = values_of(profiles)
    book = book or SignatureBook()
    statuses = book.audit(profiles)

    rows: list[tuple[str, str]] = []
    for path, st in statuses.items():
        prov = REGISTRY.get(path)
        if prov is None or not prov.needs_signature:
            continue
        if not include_signed and st.state in (
            STATE_SIGNED, STATE_NOT_REQUIRED
        ):
            continue
        if confidence and prov.confidence != confidence:
            continue
        if document and (
            not prov.ref or document.lower() not in prov.ref.document.lower()
        ):
            continue
        rows.append((path, st.state))

    rows.sort(key=lambda r: _risk_key(r[0], r[1]))
    if limit:
        rows = rows[:limit]

    path_out.parent.mkdir(parents=True, exist_ok=True)
    with path_out.open("w", newline="", encoding=ENCODING) as fh:
        wr = csv.writer(fh)
        wr.writerow(HEADER)
        for path, state in rows:
            prov = REGISTRY.get(path)
            value = values.get(path)
            wr.writerow([
                path, repr(value), prov.unit, prov.confidence,
                prov.safety_direction,
                prov.ref.document if prov.ref else "",
                prov.ref.edition if prov.ref else "",
                prov.ref.clause if prov.ref else "",
                prov.note, " ".join(rules_using(path)),
                state, value_digest(value),
                "", "", "", "", "",
            ])
    return path_out, len(rows)


# ═══════════════ الاستيراد ═══════════════

@dataclass(frozen=True, slots=True)
class RowProblem:
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class Correction:
    path: str
    current: str
    proposed: str
    clause: str
    reviewer: str
    note: str


@dataclass
class ImportOutcome:
    signed: list[str] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    skipped: int = 0
    problems: list[RowProblem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _missing_columns(fieldnames: list[str] | None) -> list[str]:
    have = set(fieldnames or ())
    return [c for c in HEADER if c not in have]


def import_worksheet(
    path_in: Path,
    *,
    book: SignatureBook,
    profiles: dict[str, Any] | None = None,
) -> ImportOutcome:
    """
    يقرأ ورقة معبَّأة. يوقّع صفوف `ok` فقط.

    ثلاث بوابات على كل صفّ سليم، وكلها ضرورية:
      • المسار موجود في السجل ويحتاج توقيعًا.
      • تلبيد القيمة في الورقة يطابق القيمة في الكود **الآن** — فورقة
        قديمة بعد تعديل رقم تُرفض بدل أن توقّع قيمة لم يرَها المراجع.
      • المراجع أثبت فقرة وكتب اسمه.

    القيمة تُقرأ من ملف الكود لا من الورقة قصدًا: لو حرّر أحدهم عمود
    `current_value` يدويًا فلا أثر له. التوقيع دائمًا على ما في الكود.
    """
    profiles = profiles or default_profiles()
    values = values_of(profiles)
    out = ImportOutcome()

    with path_in.open(newline="", encoding=ENCODING) as fh:
        rd = csv.DictReader(fh)
        missing = _missing_columns(rd.fieldnames)
        if missing:
            out.problems.append(RowProblem(
                "<الملف>", f"أعمدة ناقصة: {', '.join(missing)}"
            ))
            return out

        for raw in rd:
            path = (raw.get("path") or "").strip()
            if not path:
                continue
            verdict = (raw.get("verdict") or "").strip().lower()
            reviewer = (raw.get("reviewer") or "").strip()
            clause = (raw.get("clause_confirmed") or "").strip()
            note = (raw.get("review_note") or "").strip()

            if verdict in VERDICT_SKIP:
                out.skipped += 1
                continue

            prov = REGISTRY.get(path)
            if prov is None:
                out.problems.append(
                    RowProblem(path, "مسار غير موجود في سجل الإثبات")
                )
                continue
            if not prov.needs_signature:
                out.problems.append(
                    RowProblem(path, "معامل محرك — لا يُوقَّع")
                )
                continue

            live = values.get(path)
            sheet_digest = (raw.get("value_digest") or "").strip()
            if sheet_digest and sheet_digest != value_digest(live):
                out.problems.append(RowProblem(
                    path,
                    f"القيمة تغيّرت في الكود بعد تصدير الورقة "
                    f"(الآن {live!r}) — أعد التصدير قبل التوقيع",
                ))
                continue

            if verdict in VERDICT_WRONG:
                proposed = (raw.get("correct_value") or "").strip()
                if not proposed:
                    out.problems.append(RowProblem(
                        path, "حُكم عليه بالخطأ بلا قيمة صحيحة مقترحة"
                    ))
                    continue
                out.corrections.append(Correction(
                    path=path, current=repr(live), proposed=proposed,
                    clause=clause, reviewer=reviewer, note=note,
                ))
                continue

            if verdict not in VERDICT_OK:
                out.problems.append(RowProblem(
                    path, f"حكم غير مفهوم: {verdict!r} — استخدم ok أو wrong"
                ))
                continue

            try:
                book.sign(
                    path, live, by=reviewer, clause=clause, note=note
                )
                out.signed.append(path)
            except (KeyError, ValueError) as exc:
                out.problems.append(RowProblem(path, str(exc)))

    return out


def write_corrections(out: ImportOutcome, path_out: Path) -> Path | None:
    """
    ملف التصحيحات: ما حكم المراجع بخطئه، ولم يُوقَّع.

    لا يعدّل ملفات الكود — التعديل قرار يُتّخذ بعد `codes impact`، لا
    أثناء استيراد ورقة. لكل صفّ الأمر الجاهز الذي يقيس الأثر.
    """
    if not out.corrections:
        return None
    path_out.parent.mkdir(parents=True, exist_ok=True)
    with path_out.open("w", newline="", encoding=ENCODING) as fh:
        wr = csv.writer(fh)
        wr.writerow([
            "path", "value_in_code", "proposed_value", "clause_confirmed",
            "reviewer", "note", "impact_command",
        ])
        for c in out.corrections:
            wr.writerow([
                c.path, c.current, c.proposed, c.clause, c.reviewer, c.note,
                f'planforge codes impact "{c.path}" {c.proposed}',
            ])
    return path_out


def progress(book: SignatureBook) -> dict[str, Any]:
    """تقدّم المراجعة بحسب الوثيقة — يقيس ما بقي لا ما أُنجز فقط."""
    profiles = default_profiles()
    statuses = book.audit(profiles)
    by_doc: dict[str, dict[str, int]] = {}
    for path, st in statuses.items():
        prov = REGISTRY.get(path)
        if prov is None or not prov.needs_signature:
            continue
        doc = prov.ref.document if prov.ref else "—"
        slot = by_doc.setdefault(
            doc, {"signed": 0, "stale": 0, "unsigned": 0}
        )
        slot[st.state if st.state in slot else "unsigned"] += 1
    return {
        "as_of": date.today().isoformat(),
        "fingerprint": book.fingerprint(profiles),
        "by_document": by_doc,
    }
