"""
ترتيب البدائل: خصائص مقيسة + وزن خطي.

لا تعلّم آلي الآن، لكن كل بديل يُحفَظ مع متجه خصائصه، وكل اختيار يسجّله
المهندس يُخزَّن كتفضيل زوجي. بعد بضع مئات من الاختيارات تُدرَّب أوزان
حقيقية على قرارات هذا المهندس بالتحديد — بلا لمس أي قيد صلب.

الأوزان الحالية **تخمينية بالكامل**. غرض `planforge choose` أن تُستبدل.
والبيانات تبقى محليًا: لا شيء يُرسل خارج الجهاز.
"""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from planforge.codes.uk.detail_profile import DETAIL
from planforge.drawing.model import Drawing
from planforge.enums import CIRCULATION, HABITABLE, WET
from planforge.fixtures.result import KitchenAudit
from planforge.model.brief import Brief
from planforge.rules.core import ComplianceReport
from planforge.units import area_m2

CHOICES_FILE = "choices.jsonl"
FACADE_TOL_MM = DETAIL.facade_tol_mm
ALIGN_TOL_MM = DETAIL.vertical_align_tol_mm
WET_STACK_MIN = DETAIL.wet_stack_min_overlap


@dataclass(frozen=True)
class Features:
    clear_gia_m2: float
    circulation_ratio: float
    mean_area_error: float
    worst_area_error: float
    unfurnishable_rooms: int
    aspect_penalty: float
    external_wall_per_habitable: float
    wet_stack_ratio: float
    structural_alignment_ratio: float
    wall_length_per_m2: float
    door_count: int
    kitchen_run_margin: float
    errors: int
    warnings: int


@dataclass(frozen=True)
class RankWeights:
    circulation_ratio: float = -120.0
    mean_area_error: float = -80.0
    worst_area_error: float = -40.0
    unfurnishable_rooms: float = -600.0
    aspect_penalty: float = -25.0
    external_wall_per_habitable: float = 18.0
    wet_stack_ratio: float = 90.0
    structural_alignment_ratio: float = 70.0
    wall_length_per_m2: float = -22.0
    kitchen_run_margin: float = 30.0
    warnings: float = -8.0
    errors: float = -5000.0

    @classmethod
    def load(cls, path: Path | None) -> RankWeights:
        if path is None or not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(
                f"أوزان غير معروفة في {path}: {sorted(unknown)}"
            )
        return cls(**raw)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def _area_errors(dwg: Drawing, brief: Brief) -> list[float]:
    targets = {
        r.id: r.target_area_mm2 for r in brief.rooms if r.target_area_mm2
    }
    return [
        abs(r.area - targets[r.id]) / targets[r.id]
        for st in dwg.storeys for r in st.rooms
        if r.id in targets
    ]


def _external_wall_length(dwg: Drawing) -> tuple[int, int]:
    """(طول واجهات غرف السكن، عددها)."""
    total = 0
    count = 0
    for st in dwg.storeys:
        x, y, w, h = st.envelope
        for r in st.rooms:
            if r.type not in HABITABLE:
                continue
            count += 1
            if r.x <= x + FACADE_TOL_MM:
                total += r.h
            if r.x2 >= x + w - FACADE_TOL_MM:
                total += r.h
            if r.y <= y + FACADE_TOL_MM:
                total += r.w
            if r.y2 >= y + h - FACADE_TOL_MM:
                total += r.w
    return total, count


def _wet_stack(dwg: Drawing) -> tuple[int, int]:
    ordered = sorted(dwg.storeys, key=lambda s: s.index)
    stacked = total = 0
    for lower, upper in zip(ordered, ordered[1:]):
        below = [r for r in lower.rooms if r.type in WET]
        for r in upper.rooms:
            if r.type not in WET:
                continue
            total += 1
            for o in below:
                dx = min(r.x2, o.x2) - max(r.x, o.x)
                dy = min(r.y2, o.y2) - max(r.y, o.y)
                if dx > 0 and dy > 0 and (
                    dx * dy > min(r.area, o.area) * WET_STACK_MIN
                ):
                    stacked += 1
                    break
    return stacked, total


def _alignment(dwg: Drawing) -> tuple[int, int]:
    ordered = sorted(dwg.storeys, key=lambda s: s.index)
    aligned = total = 0
    for lower, upper in zip(ordered, ordered[1:]):
        lines = {(r.axis, r.coord) for r in lower.runs}
        for r in upper.runs:
            total += 1
            if any(
                a is r.axis and abs(c - r.coord) <= ALIGN_TOL_MM
                for a, c in lines
            ):
                aligned += 1
    return aligned, total


def extract(
    dwg: Drawing,
    brief: Brief,
    layout_rep: ComplianceReport,
    drawing_rep: ComplianceReport,
    fixture_rep: ComplianceReport,
    kitchens: dict[str, KitchenAudit],
) -> Features:
    rooms = [r for st in dwg.storeys for r in st.rooms]
    gia = dwg.total_gia_mm2
    circ = sum(r.area for r in rooms if r.type in CIRCULATION)

    errs = _area_errors(dwg, brief)
    aspects = [
        max(0.0, max(r.w, r.h) / min(r.w, r.h) - 1.5)
        for r in rooms
        if r.type not in CIRCULATION and min(r.w, r.h) > 0
    ]
    ext_len, hab_count = _external_wall_length(dwg)
    stacked, wet_total = _wet_stack(dwg)
    aligned, run_total = _alignment(dwg)

    wall_len = sum(r.length for st in dwg.storeys for r in st.runs)
    doors = sum(
        1 for st in dwg.storeys for o in st.openings
        if o.room_b is not None
    )
    margin = (
        min(a.run_margin for a in kitchens.values()) if kitchens else 0.0
    )
    gia_m2 = area_m2(gia) if gia else 0.0

    return Features(
        clear_gia_m2=round(gia_m2, 2),
        circulation_ratio=round(circ / gia, 4) if gia else 0.0,
        mean_area_error=round(sum(errs) / len(errs), 4) if errs else 0.0,
        worst_area_error=round(max(errs), 4) if errs else 0.0,
        unfurnishable_rooms=sum(
            1 for v in fixture_rep.violations if v.rule_id == "FIX-001"
        ),
        aspect_penalty=round(sum(aspects), 3),
        external_wall_per_habitable=round(
            ext_len / max(1, hab_count) / 1000, 3
        ),
        wet_stack_ratio=(
            round(stacked / wet_total, 3) if wet_total else 1.0
        ),
        structural_alignment_ratio=(
            round(aligned / run_total, 3) if run_total else 1.0
        ),
        wall_length_per_m2=round(
            (wall_len / 1000) / max(1e-6, gia_m2), 4
        ),
        door_count=doors,
        kitchen_run_margin=round(margin, 3),
        errors=sum(
            len(rep.errors)
            for rep in (layout_rep, drawing_rep, fixture_rep)
        ),
        warnings=sum(
            len(rep.warnings)
            for rep in (layout_rep, drawing_rep, fixture_rep)
        ),
    )


def score(f: Features, w: RankWeights = RankWeights()) -> float:
    """درجة الترتيب: الأعلى أفضل."""
    total = 0.0
    for name, weight in asdict(w).items():
        total += weight * float(getattr(f, name))
    return round(total, 3)


def record_choice(
    out_dir: Path, chosen: int, features: list[Features], project: str
) -> Path:
    """
    تسجيل اختيار المهندس كتفضيلات زوجية.

    مجموعة تدريب تُبنى من اليوم الأول بلا أي نموذج. البيانات محلّية
    بالكامل — لا شيء يُرسل إلى أي جهة.
    """
    if not (0 <= chosen < len(features)):
        raise ValueError(
            f"الرقم {chosen} خارج المدى 0..{len(features) - 1}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / CHOICES_FILE
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "chosen": chosen,
        "pairs": [
            {"winner": asdict(features[chosen]), "loser": asdict(f)}
            for i, f in enumerate(features) if i != chosen
        ],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
