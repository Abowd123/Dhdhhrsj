"""
سجلات إثبات أرقام التجهيزات.

هذا الملف **أخطر من `provenance_uk.py` عمليًا**: أرقامه لا تُستخدم في
التدقيق فقط، بل تُستنبط منها الأبعاد الدنيا التي تُغذّي المُحلّل رجوعًا
(`derive_min_dimensions`). رقم خاطئ في حيّز استخدام يشوّه كل مخطط
مولَّد، لا حكمًا واحدًا. راجعه قبل ملف الكود العام.

الحقول المنطقية مسجَّلة أيضًا، وليست تفصيلة: `needs_drain` يقود فحص
أعمدة الصرف، و`against_wall` يقود قيود الحزم، و`is_worktop` يقود تدقيق
المطبخ. كلها قرارات تخطيطية تُراجع، لا بيانات كتالوج تُنسخ.
"""
from __future__ import annotations
from planforge.codes.provenance import (
    CONVENTION_REF, REGISTRY, Confidence, Provenance, SafetyDirection as SD,
)
from planforge.codes.uk.fixtures_profile import FIX
from planforge.codes.uk.provenance_uk import ADM, BS6465, _ref

CATALOGUE_REF = CONVENTION_REF
"""كتالوجات المصنّعين عرفٌ سوقي لا نصّ — لا تُنسب إلى فقرة."""


def _add(
    path: str, unit: str, conf: Confidence, ref, note: str = "",
    direction: SD = SD.EXACT,
) -> None:
    REGISTRY.add(Provenance(path, unit, conf, ref, note, direction))


_add("fix.edition", "-", Confidence.ENGINE, None, "وسم الإصدار")
_add("fix.verified_by", "-", Confidence.ENGINE, None, "اسم المُصدِّق")

# ═══════════════ الكتالوج ═══════════════

_SANITARY = {
    "WC": "Table 2 / figures — WC pan",
    "BASIN": "Table 2 / figures — wash basin",
    "BATH": "Table 2 / figures — bath",
    "SHOWER": "Table 2 / figures — shower tray",
    "SINK": "Table 2 / figures — kitchen sink",
}

for _code, _spec in sorted(FIX.catalogue.items()):
    _clause = _SANITARY.get(_code)
    body_conf = Confidence.QUOTED if _clause else Confidence.CONVENTION
    body_ref = _ref(BS6465, _clause) if _clause else CATALOGUE_REF

    for _dim in ("w", "d"):
        _add(
            f"fix.catalogue[{_code}].{_dim}", "mm", body_conf, body_ref,
            "مقاس الجسم. يطابق كتالوجات المصنّعين عادةً، فخطؤه محدود "
            "الأثر: يُزيح التجهيز ولا يُسقط الغرفة.",
            SD.CONSERVATIVE,
        )
    for _dim in ("activity_w", "activity_d"):
        _add(
            f"fix.catalogue[{_code}].{_dim}", "mm", Confidence.RECALLED,
            _ref(BS6465, "Figures — activity space") if _clause
            else CATALOGUE_REF,
            "حيّز الاستخدام. **يُستنبط منه الحد الأدنى للغرفة**، فخطؤه "
            "يشوّه المخططات المولَّدة كلها لا حكمًا واحدًا. أعلى أثرٍ "
            "لأصغر رقم.",
            SD.PERMISSIVE,
        )

    _add(
        f"fix.catalogue[{_code}].against_wall", "-",
        Confidence.CONVENTION, CATALOGUE_REF,
        "هل يُثبَّت ظهره إلى جدار؟ قرار تخطيطي يقود قيود الحزم: "
        "التجهيز الحر يتحرّك في وسط الغرفة، والمثبَّت يستهلك جدارًا.",
        SD.CONSERVATIVE,
    )
    _add(
        f"fix.catalogue[{_code}].needs_drain", "-",
        Confidence.CONVENTION,
        _ref(BS6465, "— drainage connections") if _clause else CATALOGUE_REF,
        "هل يحتاج وصلة صرف؟ يقود هدف الحزم (التقريب من عمود المواسير) "
        "وفحص FIX-004.",
        SD.CONSERVATIVE,
    )
    _add(
        f"fix.catalogue[{_code}].is_worktop", "-",
        Confidence.CONVENTION, CATALOGUE_REF,
        "هل يُحسب ضمن طول المنضدة؟ يقود تدقيق المطبخ.",
        SD.CONSERVATIVE,
    )

# ═══════════════ الدوران والوصول ═══════════════

for _std in ("M4(1)", "M4(2)", "M4(3)"):
    _add(
        f"fix.turning_space[{_std}]", "mm", Confidence.RECALLED,
        _ref(ADM, "para 3.x — wheelchair turning and manoeuvring"),
        "1500 مم دائرة دوران، و1200×1500 مناورة على شكل T. القيمة "
        "المخزَّنة رقم واحد يُفرض مربعًا حرًّا، وهذا تبسيط مُعلن: "
        "المناورة على شكل T تحتاج نمذجة أدقّ.",
        SD.PERMISSIVE,
    )
    _add(
        f"fix.kitchen_gangway[{_std}]", "mm", Confidence.RECALLED,
        _ref(ADM, "para 3.x — kitchen circulation"),
        "عرض المجاز بين المناضد المتقابلة.", SD.PERMISSIVE,
    )

# ═══════════════ المطبخ ═══════════════

for _bs in sorted(FIX.worktop_run_by_bedspaces):
    _add(
        f"fix.worktop_run_by_bedspaces[{_bs}]", "mm",
        Confidence.CONVENTION, CATALOGUE_REF,
        "طول المنضدة المطلوب بحسب عدد الأشخاص. عرف إسكاني بريطاني لا "
        "نصّ — يظهر في FIX-003 كخطأ لأن قصوره يُنتج مطبخًا لا يعمل.",
        SD.CONSERVATIVE,
    )

_KITCHEN_CONV = (
    ("worktop_depth", "mm", "عمق المنضدة — يُخصم من عرض الغرفة لحساب المجاز"),
    ("worktop_height", "mm",
     "ارتفاع المنضدة. يحدّد أي نافذة تقطع الطول المتاح: ما جلستها أعلى "
     "منه يمرّ فوق المنضدة. تفصيلة تفرّق بين مطبخ يعمل وآخر يبدو كافيًا."),
    ("worktop_beside_hob_min", "mm", "منضدة بجانب الطبّاخ — سلامة"),
    ("worktop_beside_sink_min", "mm", "مصفاة بجانب الحوض"),
    ("hob_to_sink_min", "mm", "منضدة فاصلة بين الطبّاخ والحوض"),
    ("hob_from_corner_min", "mm", "ابتعاد الطبّاخ عن الزاوية"),
    ("corner_loss_mm", "mm",
     "الزاوية غير المستخدَمة عند التقاء ضلعين متعامدين"),
)
for _p, _unit, _note in _KITCHEN_CONV:
    _add(f"fix.{_p}", _unit, Confidence.CONVENTION, CATALOGUE_REF,
         _note, SD.CONSERVATIVE)

_add("fix.hob_under_window_forbidden", "-", Confidence.CONVENTION,
     CATALOGUE_REF,
     "منع الطبّاخ تحت النافذة. عرف سلامة راسخ (الستائر والتيار الهوائي) "
     "لا فقرة قانونية.", SD.CONSERVATIVE)
_add("fix.door_swing_clear_of_activity", "-", Confidence.CONVENTION,
     CATALOGUE_REF,
     "هل يجب أن يبقى قوس دوران الباب خارج حيّز الاستخدام؟ يُفرض لغير "
     "M4(1) فقط — قرار تخطيطي يوسّع الغرف المطلوبة أو يضيّقها.",
     SD.CONSERVATIVE)


def register_all() -> None:
    return None
