"""
توقيع الأرقام، مقفولًا بالقيمة.

التوقيع يشمل تلبيد القيمة. تغيّرت القيمة ⟹ بطل التوقيع تلقائيًا. لا
يوجد توقيع «على المستقبل»: من وقّع 2150 لم يوقّع 2100. وهذا ما يجعل
التوقيع إقرارًا مهنيًا لا خطوة إدارية.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any
from planforge.codes.provenance import REGISTRY, value_digest, values_of

DEFAULT_PATH = Path("code_signatures.json")
FILE_VERSION = "1"

STATE_SIGNED = "signed"
STATE_STALE = "stale"
STATE_UNSIGNED = "unsigned"
STATE_NOT_REQUIRED = "not_required"
TRUSTED_STATES = frozenset({STATE_SIGNED, STATE_NOT_REQUIRED})


@dataclass(frozen=True, slots=True)
class Signature:
    path: str
    value_digest: str
    value_repr: str
    signed_by: str
    signed_on: str
    clause_confirmed: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class Status:
    path: str
    state: str
    signature: Signature | None
    current_repr: str

    @property
    def trusted(self) -> bool:
        return self.state in TRUSTED_STATES


class SignatureBook:
    def __init__(self, sigs: dict[str, Signature] | None = None) -> None:
        self._sigs: dict[str, Signature] = dict(sigs or {})

    # ─────────── قرص ───────────

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> SignatureBook:
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("file_version")
        if version != FILE_VERSION:
            raise ValueError(
                f"إصدار ملف توقيعات غير مدعوم: {version} "
                f"(المدعوم {FILE_VERSION})"
            )
        return cls({
            s["path"]: Signature(**s) for s in raw.get("signatures", [])
        })

    def save(self, path: Path = DEFAULT_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "file_version": FILE_VERSION,
            "signatures": [asdict(self._sigs[p]) for p in sorted(self._sigs)],
        }
        path.write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def __len__(self) -> int:
        return len(self._sigs)

    # ─────────── توقيع ───────────

    def sign(
        self, path: str, value: Any, *, by: str, clause: str, note: str = ""
    ) -> Signature:
        """
        ثلاث بوابات، وكلها ضرورية:
          • المسار مسجَّل ويحتاج توقيعًا.
          • للموقِّع اسم — التوقيع إقرار شخصي.
          • أُثبتت الفقرة — «راجعتها» ليس إثباتًا، ورقم الفقرة إثبات.
        """
        prov = REGISTRY.get(path)
        if prov is None:
            raise KeyError(f"لا سجل إثبات للمسار {path}")
        if not prov.needs_signature:
            raise ValueError(f"{path}: معامل محرك لا يحتاج توقيعًا")
        if not by.strip():
            raise ValueError("التوقيع يلزمه اسم موقِّع")
        if not clause.strip():
            raise ValueError(
                "التوقيع يلزمه إثبات الفقرة — اكتب الفقرة التي قرأتها فعلًا"
            )
        sig = Signature(
            path=path,
            value_digest=value_digest(value),
            value_repr=repr(value),
            signed_by=by.strip(),
            signed_on=date.today().isoformat(),
            clause_confirmed=clause.strip(),
            note=note.strip(),
        )
        self._sigs[path] = sig
        return sig

    def revoke(self, path: str) -> bool:
        return self._sigs.pop(path, None) is not None

    # ─────────── فحص ───────────

    def status_of(self, path: str, value: Any) -> Status:
        prov = REGISTRY.get(path)
        if prov is not None and not prov.needs_signature:
            return Status(path, STATE_NOT_REQUIRED, None, repr(value))
        sig = self._sigs.get(path)
        if sig is None:
            return Status(path, STATE_UNSIGNED, None, repr(value))
        if sig.value_digest != value_digest(value):
            return Status(path, STATE_STALE, sig, repr(value))
        return Status(path, STATE_SIGNED, sig, repr(value))

    def audit(self, profiles: dict[str, Any]) -> dict[str, Status]:
        return {
            path: self.status_of(path, value)
            for path, value in sorted(values_of(profiles).items())
        }

    def tally(self, profiles: dict[str, Any]) -> dict[str, int]:
        out = {
            STATE_SIGNED: 0, STATE_STALE: 0,
            STATE_UNSIGNED: 0, STATE_NOT_REQUIRED: 0,
        }
        for st in self.audit(profiles).values():
            out[st.state] += 1
        return out

    def fingerprint(self, profiles: dict[str, Any]) -> str:
        """
        بصمة حالة الاعتماد كلها.

        تُختم في التقارير والـDXF، فيمكن إثبات أن مخرجًا بعينه وُلِّد بحالة
        أرقام بعينها — بلا حفظ الأرقام نفسها في المخرج.
        """
        rows = sorted(
            f"{p}:{s.state}:{value_digest(s.current_repr)}"
            for p, s in self.audit(profiles).items()
        )
        return hashlib.sha256(
            "\n".join(rows).encode("utf-8")
        ).hexdigest()[:12]


def default_profiles() -> dict[str, Any]:
    """
    ملفات الكود مع ضمان تسجيل إثباتها.

    الاستيرادات ضرورية لا تجميلية: السجل يُملأ عند تحميل الوحدة، ونداءٌ
    على `coverage()` قبلها يُخرج كل رقم فجوةً.
    """
    from planforge.codes.uk.detail_profile import DETAIL
    from planforge.codes.uk.fixtures_profile import FIX
    from planforge.codes.uk.profile import UK
    import planforge.codes.uk.provenance_uk        # noqa: F401
    import planforge.codes.uk.provenance_fixtures  # noqa: F401
    import planforge.codes.uk.provenance_detail    # noqa: F401
    return {"uk": UK, "fix": FIX, "detail": DETAIL}
