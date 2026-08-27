# ملاحظة تطبيق المرحلة B

طُبّقت كل بنود `المرحلة_B_مصدر_واحد_لكل_رقم.md` على الأرشيف
`planforge_patchA_applied.zip`. تفاصيل التطبيق والانحرافات عن النص
الحرفي للمستند:

## ما طُبّق كما هو

- ملفان جديدان: `codes/uk/detail_profile.py` (`DETAIL`) و
  `codes/uk/provenance_detail.py`.
- `codes/signing.py::default_profiles` و`golden.py::_resolve` يضيفان
  الجذر `"detail"`.
- `golden.py::override` يستدعي `_invalidate_caches()` بعد الكتابة
  وفي `finally` لإبطال `minimal_envelope.cache_clear()`.
- إزالة الثوابت الستة المكرَّرة من `drawing/placement.py` و
  `solver/refine.py` وربطها بـ`DETAIL` (تحقّقتُ أنّ AST للطرفين يشير
  الآن لنفس حقل `DETAIL` حرفيًا — لا قيمة مكرَّرة متبقية).
- `rules/drawing_rules.py`, `rules/fixture_rules.py`,
  `rules/geometric.py`, `geometry/tiling.py`, `fixtures/kitchen.py`,
  `fixtures/pack.py`, `geometry/lines.py`, `ranking.py`,
  `drawing/annotate.py` — كل الثوابت المذكورة صراحةً في المستند صارت
  تُقرأ من `DETAIL`.
- خريطة الاستناد (`codes/usage.py::RULE_DEPENDENCIES`) وُسِّعت بمسارات
  `detail.*` كما ورد في المستند (DRW-007/009/010/011/014/015/016،
  FIX-001/003/004/005، SOL-001).
- اختباران جديدان في `tests/test_provenance.py`:
  `test_every_signable_path_is_read_by_some_rule` و
  `test_detail_profile_is_covered`.

## انحرافان عن النص الحرفي — وسببهما

1. **`Provenance(..., needs_signature=True)` غير صالح.**
   `needs_signature` في `codes/provenance.py` خاصية محسوبة
   (`@property`) من `confidence`، لا وسيطًا لمُنشئ `dataclass`.
   استدعاؤها بهذا الاسم كوسيط كان سيرفع `TypeError` فورًا. حذفتُ
   `needs_signature=True` من كلا حلقتي `provenance_detail.py`
   (CONVENTION وENGINE) والاعتماد على الحساب التلقائي: يبقى صحيحًا
   لعناصر CONVENTION (`needs_signature=True` تلقائيًا لأن الثقة ليست
   `ENGINE`)، ويطابق نص المستند نفسه لعناصر ENGINE («معاملات محرك …
   ولا تُوقَّع» — أي `needs_signature=False`، وهو ما تُنتجه الخاصية
   المحسوبة أصلًا).

2. **`structural_min_ratio` و`vertical_align_tol_mm` ثوابتهما الفعلية
   في `drawing/walls.py` لا `rules/drawing_rules.py`.** المستند وضع
   سطري `ALIGN_TOL_MM` و(ضمنًا) `STRUCTURAL_MIN_RATIO` تحت عنوان
   `rules/drawing_rules.py`، لكن الثابتين المكرَّرين فعليًا (`= 0.60`
   و`= 60`) معرَّفان في `drawing/walls.py` ويُستخدمان هناك في
   `_classify` لتصنيف الجدار الحامل. تحديثهما في `drawing_rules.py`
   وحده كان سيترك النسخة الحقيقية في `walls.py` بلا تغيير — نقيض هدف
   «مصدر واحد لكل رقم». صحّحتُ `walls.py` ليقرأ من `DETAIL`، وأبقيتُ في
   `drawing_rules.py` فقط الثابتين اللذين يُستخدمان فيه فعلًا
   (`MIN_WALL_SLIVER_MM`, `SWING_CLEARANCE_MM`).

## عيب جديد كشفه تفعيل الفحص — لم يذكره المستند

`test_every_signable_path_is_read_by_some_rule` يسقط الآن على **19**
مسارًا لا 3: الثلاثة المعروفة سلفًا
(`fix.worktop_beside_hob_min`, `fix.worktop_beside_sink_min`,
`fix.catalogue[*].is_worktop` — تتوسّع لـ17 مسارًا فرديًا) **زائد**
`detail.door_head_mm`.

`door_head_mm` يُخزَّن في `PlacedOpening.head_mm` (البيانات الوصفية
لعتب الفتحة) ولا يقرؤه أي حكم مُصرَّح في `RULE_DEPENDENCIES` — يظهر
فقط في هندسة الرسم دون أن يقود قرار امتثال. لم يذكره المستند ضمن
الأرقام الميتة المعروفة، وتحقّقتُ يدويًا أنه فعلًا غير مقروء بحكم.
القرار (كما مع الثلاثة الأخرى) متروك لرقعة لاحقة: إما ربطه بحكم فعلي
(مثلًا فحص منسوب عتب موحَّد بين الأبواب) أو إسقاط توقيعه.

## التحقق المُجرى (بلا شبكة، فبلا pytest كامل)

بيئة التنفيذ هنا بلا اتصال شبكة، فتعذّر تثبيت `pydantic`/`ortools`
وتشغيل `pytest` كاملة. تحقّقتُ بدلًا من ذلك:

- `ast.parse` لكل ملفات `src/` و`tests/` — لا أخطاء صياغة.
- فحص دوري تلقائي لشجرة استيراد الحزمة كاملة (67 وحدة) — لا حلقات.
- تشغيل مباشر (بلا pytest) لِـ:
  - `coverage(default_profiles())` → **0 فجوة**، 250 قيمة معدودة.
  - فحص اليتامى (orphans) أعلاه → 19 كما هو موضّح.
  - `test_detail_profile_is_covered` يدويًا → 28 مسار `detail.*` معدود
    (الحد الأدنى المطلوب 20).
  - كل أنماط `RULE_DEPENDENCIES` تُحلّ عبر `expand()` بلا `KeyError`.
  - `golden._resolve`/`override` مع الجذر الجديد `detail` — تعمل
    وتُرجع القيمة الأصلية بعد الخروج.
  - مقارنة AST للثوابت الستة المكرَّرة سابقًا بين `placement.py` و
    `refine.py` — تشير الآن لنفس حقل `DETAIL` حرفيًا في كلا الملفين.

لم يُشغَّل: أي اختبار يستورد `planforge.model.brief` (يحتاج
`pydantic`) أو `fixtures/pack.py` (يحتاج `ortools`) فعليًا، ولا
`pytest` بمجموعها. يُنصح بتشغيل:

```bash
pip install -e .
pytest tests/test_provenance.py -q
planforge codes audit
```

فور توفر بيئة متصلة، قبل الاعتماد النهائي.
