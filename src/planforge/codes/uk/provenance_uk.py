"""
سجلات إثبات أرقام المملكة المتحدة.

‼ كل سجل هنا غير موقَّع حتى يوقّعه مهندس. الطريق العملي:
`planforge codes worksheet -d "Approved Document B" --limit 25`.

`safety_direction` أهم حقل للترتيب: الأرقام `permissive` خطؤها يُمرّر
مخالفة، فتُراجع أولًا. و`confidence = recalled` تعني أن الرقم كُتب من
الذاكرة بلا فتح النص. اجتماعهما (`is_high_risk`) هو رأس القائمة.
"""
from __future__ import annotations
from planforge.codes.provenance import (
    CONVENTION_REF, REGISTRY, CodeRef, Confidence, Provenance,
    SafetyDirection as SD,
)
from planforge.codes.uk.profile import UK

ADM = CodeRef(
    "Approved Document M Vol 1 — Access to and use of buildings: dwellings",
    "2015 (incl. 2016 amendments)", "", url="https://www.gov.uk/",
)
ADB = CodeRef(
    "Approved Document B Vol 1 — Fire safety: dwellings",
    "2019 (incl. 2020 & 2022 amendments)", "",
)
ADF = CodeRef("Approved Document F Vol 1 — Ventilation: dwellings", "2021", "")
ADG = CodeRef("Approved Document G — Sanitation, hot water and efficiency",
              "2015 (incl. 2016 amendments)", "")
ADK = CodeRef("Approved Document K — Protection from falling", "2013", "")
NDSS = CodeRef(
    "Technical housing standards — nationally described space standard",
    "2015", "",
)
BS6465 = CodeRef(
    "BS 6465-2 — Sanitary installations: space recommendations", "2017", "",
)


def _ref(base: CodeRef, clause: str, page: str = "") -> CodeRef:
    return CodeRef(base.document, base.edition, clause, page, base.url)


def _add(
    path: str,
    unit: str,
    conf: Confidence,
    ref: CodeRef | None,
    note: str = "",
    direction: SD = SD.EXACT,
) -> None:
    REGISTRY.add(Provenance(path, unit, conf, ref, note, direction))


# ═══════════════ NDSS 2015 ═══════════════

_add("uk.edition", "-", Confidence.ENGINE, None,
     "وسم الإصدار — نصّ لا رقم")
_add("uk.verified_by", "-", Confidence.ENGINE, None,
     "اسم المُصدِّق — يُملأ يدويًا")

for _key in sorted(UK.ndss_gia_table):
    _add(
        f"uk.ndss_gia_table[{_key}]", "mm2", Confidence.RECALLED,
        _ref(NDSS, f"Table 1 — {_key}"),
        "صفٌّ من جدول GIA. الجدول كله كُتب من الذاكرة، وهو أكبر ما في "
        "الملف وأكثره عرضة للخطأ. راجعه صفًّا صفًّا — لهذا فُصل كل صف "
        "بمساره كي يُوقَّع وحده.",
        SD.PERMISSIVE,
    )

for _t, _clause in (
    ("bedroom_single", "Table 1 / para 10 — single bedroom"),
    ("bedroom_double", "Table 1 / para 10 — double bedroom"),
    ("bedroom_main", "Table 1 / para 10 — double bedroom"),
):
    _add(
        f"uk.bedroom_min_area[{_t}]", "mm2", Confidence.RECALLED,
        _ref(NDSS, _clause),
        "NDSS ينصّ 7.5 م² للفردية و11.5 م² للمزدوجة. تحقّق من الرقم ومن "
        "إسناد bedroom_main إلى المزدوجة — النصّ لا يفرّق بينهما، والتفريق "
        "هنا في العرض لا في المساحة.",
        SD.PERMISSIVE,
    )
    _add(
        f"uk.bedroom_min_width[{_t}]", "mm", Confidence.RECALLED,
        _ref(NDSS, _clause),
        "2.15 م للفردية و2.75 م للمزدوجة. القيمة المخزَّنة للمزدوجة "
        "2.55 م — راجع أي الرقمين صحيح وأيهما ينطبق على bedroom_main.",
        SD.PERMISSIVE,
    )

for _n in sorted(UK.storage_by_bedrooms):
    _add(
        f"uk.storage_by_bedrooms[{_n}]", "mm2", Confidence.RECALLED,
        _ref(NDSS, "para 9 — built-in storage"),
        "1.0 م² لسكن غرفة أو غرفتين، زائد 0.5 م² لكل غرفة إضافية. "
        "تحقّق من الأساس ومن الزيادة.",
        SD.PERMISSIVE,
    )

_add("uk.ceiling_min_height", "mm", Confidence.RECALLED,
     _ref(NDSS, "para 10 — ceiling heights"),
     "2.3 م. النصّ يشترطه على نسبةٍ من المساحة لا على كل الغرف، "
     "والنسبة في الحقل التالي.", SD.PERMISSIVE)
_add("uk.ceiling_min_coverage", "ratio", Confidence.RECALLED,
     _ref(NDSS, "para 10 — ceiling heights"),
     "75% من مساحة الأرضية. الشرط نسبةُ مساحة لا ارتفاعٌ مطلق — "
     "والمحرك يقيسه هكذا في NDSS-005.", SD.PERMISSIVE)

# ═══════════════ Approved Document M ═══════════════

for _std, _clause in (
    ("M4(1)", "Table 2 — category 1 (visitable)"),
    ("M4(2)", "Table 2 — category 2 (accessible/adaptable)"),
    ("M4(3)", "Table 2 — category 3 (wheelchair user)"),
):
    _add(
        f"uk.door_min_clear_width[{_std}]", "mm", Confidence.RECALLED,
        _ref(ADM, _clause),
        "خلوص الباب في ADM يتغيّر بعرض الممر المؤدّي إليه وبجهة الاقتراب. "
        "القيمة المخزَّنة رقم واحد لكل فئة، وهذا تبسيط مُعلن — راجع "
        "الجدول كاملًا وقرّر إن كان يلزم تفصيله.",
        SD.PERMISSIVE,
    )
    _add(
        f"uk.corridor_min_width[{_std}]", "mm", Confidence.RECALLED,
        _ref(ADM, _clause), "", SD.PERMISSIVE,
    )

_add("uk.door_side_nib", "mm", Confidence.RECALLED,
     _ref(ADM, "Diagram — approach to doors"),
     "300 مم بجانب الباب عند الاقتراب الجانبي. يُفرض في ADM-004 وفي "
     "حل الفتحات، فخطؤه يُسقط أبوابًا صالحة أو يُجيز مستحيلة.",
     SD.PERMISSIVE)
_add("uk.wc_at_entrance_storey_required", "-", Confidence.QUOTED,
     _ref(ADM, "para 2.19"),
     "دورة مياه في دور الدخول — نصّ واضح، لكن صدّق رقم الفقرة.")

# ═══════════════ Approved Document B ═══════════════

_add("uk.protected_stair_threshold", "mm", Confidence.RECALLED,
     _ref(ADB, "para 2.5–2.7"),
     "منسوب 4.5 م. **أخطر رقم في الملف**: تحته تكفي نوافذ الهروب، وفوقه "
     "يلزم سلّم محمي وأبواب مقاومة. خطؤه يقلب تصنيف المبنى كله لا حكمًا "
     "واحدًا — ابدأ منه.", SD.PERMISSIVE)
_add("uk.alt_escape_threshold", "mm", Confidence.RECALLED,
     _ref(ADB, "para 2.7–2.9"),
     "منسوب 7.5 م الذي يوجب مخرجًا بديلًا أو رشاشات. النظام لا يُنمذج "
     "أيًّا منهما، فيُصدر تحذيرًا صريحًا في ADB-004.", SD.PERMISSIVE)
_add("uk.escape_window_min_area", "mm2", Confidence.RECALLED,
     _ref(ADB, "para 2.10"), "0.33 م² فتح قابل للتشغيل", SD.PERMISSIVE)
_add("uk.escape_window_min_dim", "mm", Confidence.RECALLED,
     _ref(ADB, "para 2.10"),
     "450 مم لكل من العرض والارتفاع", SD.PERMISSIVE)
_add("uk.escape_window_sill_range", "mm", Confidence.RECALLED,
     _ref(ADB, "para 2.10"),
     "مجال جلسة النافذة 800–1100 مم. يُوقَّع كمجال واحد لأن الطرفين "
     "من فقرة واحدة.", SD.PERMISSIVE)
_add("uk.fire_door_rating_minutes", "min", Confidence.RECALLED,
     _ref(ADB, "Appendix C — Table C1"),
     "30 دقيقة (FD30) على السلّم المحمي. الرقم يُنسَّق منه وسم التصنيف "
     "في ADB-003 و DRW-014.", SD.PERMISSIVE)

# ═══════════════ Approved Document F ═══════════════

_add("uk.purge_vent_ratio", "ratio", Confidence.RECALLED,
     _ref(ADF, "Table 1.3 — purge ventilation"),
     "1/20 من مساحة الأرضية. ملاحظة تخصّ المحرك: طبقة الصقل تُولّد "
     "النوافذ على 1/16 هامشَ أمان، ثم يُقاس الحكم على 1/20 — فالرقمان "
     "مقصودان مختلفين.", SD.PERMISSIVE)

for _t in sorted(UK.extract_rates_ls, key=lambda x: x.value):
    _add(
        f"uk.extract_rates_ls[{_t.value}]", "l/s", Confidence.RECALLED,
        _ref(ADF, "Table 1.1 — extract ventilation rates"),
        "معدل الشفط. يُقرأ في ADF-002 كتحذير لا خطأ، لأن النظام لا "
        "يُنمذج المجاري.", SD.CONSERVATIVE,
    )

# ═══════════════ Approved Document G ═══════════════

_add("uk.wc_needs_lobby_to_kitchen", "-", Confidence.RECALLED,
     _ref(ADG, "— sanitary conveniences / ADF lobby requirement"),
     "منع فتح دورة المياه مباشرة على منطقة تحضير الطعام. راجع أي وثيقة "
     "تحمل الشرط فعلًا: ADG أو ADF أو لوائح محلية.", SD.PERMISSIVE)

# ═══════════════ Approved Document K ═══════════════

_STAIR = (
    ("stair_max_rise", "mm", "Table 1.1 — private stair"),
    ("stair_min_going", "mm", "Table 1.1 — private stair"),
    ("stair_max_pitch_deg", "deg", "para 1.7"),
    ("stair_2r_plus_g", "mm", "para 1.5"),
    ("stair_min_headroom", "mm", "para 1.10"),
)
for _p, _unit, _clause in _STAIR:
    _add(
        f"uk.{_p}", _unit, Confidence.RECALLED, _ref(ADK, _clause),
        "قائمة ≤220، نائمة ≥220، ميل ≤42°، 2R+G بين 550 و700. أرقام "
        "السلّم مترابطة رياضيًا، فراجعها كطقم واحد لا أرقامًا مفرّقة.",
        SD.PERMISSIVE,
    )

_add("uk.stair_min_width", "mm", Confidence.CONVENTION, CONVENTION_REF,
     "900 مم. **ليس متطلبًا قانونيًا للسلالم الخاصة** — ADK لا يفرض "
     "عرضًا أدنى لها. عرفٌ عملي، ويظهر في ADK-003 موصوفًا كذلك.",
     SD.CONSERVATIVE)

# ═══════════════ العرف المهني ═══════════════

for _t in sorted(UK.practical_min_width, key=lambda x: x.value):
    _add(
        f"uk.practical_min_width[{_t.value}]", "mm",
        Confidence.CONVENTION, CONVENTION_REF,
        "ليس متطلبًا قانونيًا. يظهر في التقارير كـ«عرف مهني» لا كفقرة. "
        "قيمته أنه يمنع غرفًا غير عملية قبل أن تصل إلى طبقة التجهيزات، "
        "حيث ترفضها بحساب أدقّ وأبطأ.",
        SD.CONSERVATIVE,
    )

_add("uk.max_aspect_default", "ratio", Confidence.CONVENTION, CONVENTION_REF,
     "سقف النسبة الباعية — تفضيل تصميمي يمنع الغرف الأنبوبية، لا متطلب.",
     SD.CONSERVATIVE)


def register_all() -> None:
    """نقطة استدعاء صريحة — الاستيراد وحده يكفي، وهذه للتوثيق."""
    return None
