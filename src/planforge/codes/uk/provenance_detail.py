"""سجلات الأرقام التفصيلية — كلها عرف، وبعضها يُصدر أخطاءً."""
from __future__ import annotations
from planforge.codes.provenance import (
    CONVENTION_REF, REGISTRY, Confidence, Provenance,
    SafetyDirection as SD,
)

_CONVENTION: tuple[tuple[str, str, str, SD], ...] = (
    ("door_frame_mm", "mm",
     "إطار الباب. يُفرض كتفًا أدنى في DRW-009 ويقرّر جدوى كل فتحة داخلية "
     "في حلّ المواضع — فتصغيره يُجيز فتحات لا تُنفَّذ.", SD.CONSERVATIVE),
    ("jamb_nib_min_mm", "mm", "كتف إنشائي أدنى عند طرف الجدار.",
     SD.CONSERVATIVE),
    ("door_head_mm", "mm", "منسوب عتب الباب.", SD.EXACT),
    ("window_head_mm", "mm",
     "منسوب عتب النافذة. يدخل في حساب المساحة القابلة للتشغيل، فيقود "
     "DRW-010 و DRW-011.", SD.PERMISSIVE),
    ("window_sill_mm", "mm", "جلسة النافذة العادية.", SD.EXACT),
    ("escape_sill_mm", "mm",
     "جلسة نافذة الهروب المولَّدة. يجب أن تبقى داخل مجال ADB "
     "(uk.escape_window_sill_range) وإلا وُلِّدت نافذة تُخالف DRW-013.",
     SD.PERMISSIVE),
    ("window_corner_offset_mm", "mm", "ابتعاد النافذة عن زاوية المبنى.",
     SD.CONSERVATIVE),
    ("window_min_width_mm", "mm",
     "أصغر نافذة تُرسم — تحتها تُبلَّغ الواجهة عاجزة.", SD.CONSERVATIVE),
    ("window_openable_fraction", "ratio",
     "نسبة الفتح الفعلي. **أخطر رقم في هذا الملف**: كان عاريًا في سطر "
     "حساب، ويقرّر وحده جواز تهوية ADF في DRW-010 و DRW-011. راجعه بحسب "
     "نوع النوافذ المحدَّد للمشروع لا افتراضًا.", SD.PERMISSIVE),
    ("generation_vent_ratio", "ratio",
     "نسبة توليد النوافذ في الصقل — أوسع من 1/20 هامشَ أمان. رفعه يُكبّر "
     "النوافذ ويُسهّل DRW-010؛ خفضه يُسقط مخططات كانت تجوز.",
     SD.CONSERVATIVE),
    ("structural_min_ratio", "ratio",
     "نسبة الاستمرارية التي تجعل الخط حاملًا. تقود تصنيف الجدار، "
     "وتصنيفُ القاطع هو شرط إصدار DRW-015.", SD.PERMISSIVE),
    ("vertical_align_tol_mm", "mm",
     "سماحية المحاذاة الرأسية في تصنيف الجدار الحامل.", SD.PERMISSIVE),
    ("align_snap_mm", "mm",
     "مدى تقريب خطوط الأدوار المتقاربة. رفعه يدمج خطوطًا مستقلة قصدًا.",
     SD.CONSERVATIVE),
    ("wall_sliver_min_mm", "mm", "أقصر مقطع جدار مقبول تنفيذيًا.",
     SD.CONSERVATIVE),
    ("swing_clearance_mm", "mm", "خلوص إضافي لدوران الباب في DRW-007.",
     SD.CONSERVATIVE),
    ("stair_stack_min_overlap", "ratio",
     "تراكب نواة السلّم بين دورين. خفضه يُجيز نواةً منقولة، فتُفقد الجدران "
     "المحيطة تصنيفها الحامل.", SD.PERMISSIVE),
    ("wet_stack_min_overlap", "ratio",
     "تراكب يكفي لاعتبار غرفتين رطبتين على عمود واحد. كان في ثلاثة "
     "مواضع: GEO-011 والترتيب وتقدير عمود المواسير.", SD.PERMISSIVE),
    ("storage_cap_ratio", "ratio",
     "أقصى ما يُنسب لغرفة نوم من مساحتها كتخزين مدمج. يقود NDSS-004: "
     "رفعه يُخفي نقص التخزين، وخفضه يُبلّغه.", SD.PERMISSIVE),
    ("drain_run_warn_mm", "mm",
     "مسار الصرف الأفقي الذي يستوجب تحذير FIX-004.", SD.CONSERVATIVE),
    ("kitchen_side_tol_mm", "mm",
     "قرب الفتحة من ضلع المطبخ لتُحسَب قاطعةً لمنضدته.", SD.PERMISSIVE),
    ("kitchen_min_segment_mm", "mm",
     "أقصر مقطع جدار يحمل وحدة مطبخ. رفعه يُسقط مطابخ صالحة، وخفضه يجمع "
     "شظايا لا تحمل شيئًا.", SD.PERMISSIVE),
    ("hob_window_proximity_mm", "mm",
     "المسافة التي يُعتبر عندها الطبّاخ تحت النافذة.", SD.CONSERVATIVE),
)

_ENGINE: tuple[tuple[str, str, str], ...] = (
    ("pack_grid_mm", "mm",
     "خشونة شبكة الحزم. معامل محرك يُصدر FIX-001 بنفسه: الغرفة تُقلَّص "
     "إليه، فيرفض غرفًا قد تنجح على شبكة أدقّ."),
    ("line_cluster_tol_mm", "mm",
     "سماحية تجميع خطوط الجدران. رفعه يدمج خطوطًا مستقلة فتتحرّك معًا."),
    ("tiling_tol_ratio", "ratio",
     "سماحية مجموع المساحات في فحص التبليط — تقود GEO-003."),
    ("facade_tol_mm", "mm", "سماحية اعتبار الغرفة ملامسة للواجهة في الترتيب."),
    ("stair_steps_max", "-", "سقف عدد خطوط القوائم المرسومة."),
    ("dim_min_span_mm", "mm", "أقصر مسافة تُبعَّد — تجميلي."),
)

REGISTRY.add(Provenance(
    "detail.edition", "-", Confidence.ENGINE, None, "وسم الإصدار"
))
REGISTRY.add(Provenance(
    "detail.verified_by", "-", Confidence.ENGINE, None,
    "اسم المُراجع، إن وُجد"
))

for _name, _unit, _note, _dir in _CONVENTION:
    REGISTRY.add(Provenance(
        f"detail.{_name}", _unit, Confidence.CONVENTION, CONVENTION_REF,
        _note, safety_direction=_dir,
    ))

for _name, _unit, _note in _ENGINE:
    REGISTRY.add(Provenance(
        f"detail.{_name}", _unit, Confidence.ENGINE, None, _note,
    ))
