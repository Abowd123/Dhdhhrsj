"""
أرقام التفاصيل: كانت ثوابت على مستوى الوحدات، وبعضها مكرَّرًا.

المشكلتان اللتان يحلّهما هذا الملف مشكلة واحدة في جوهرها:

**التكرار.** ستة أرقام كانت معرَّفة مرتين بنفس الاسم في
`drawing/placement.py` و`solver/refine.py`: إطار الباب، والكتف، وابتعاد
النافذة عن الزاوية، وعتب النافذة، وكسر الفتح. فطبقة الصقل تُولّد النافذة
على نسخة، وطبقة الرسم تُعيد حلّها على نسخة ثانية. تصحيح إحداهما يترك
الأخرى، والنتيجة نافذة مولَّدة بمعيار ومحكومٌ عليها بآخر. و`0.30` لتراكب
الغرف الرطبة كان في ثلاثة مواضع.

**الغياب عن سجل الإثبات.** `enumerate_values` تمشي على `UK` و`FIX`
وحدهما، فأي ثابت على مستوى وحدة لا يُعدّ ولا يُوقَّع ولا يُعلَن في خريطة
الاستناد. وبعضها يُصدر **أخطاءً** لا تحذيرات: `FRAME_MM` يقود DRW-009،
و`GRID` يقود FIX-001، و`window_openable_fraction` يقرّر وحده جواز تهوية
ADF. فكانت كتلة الاعتماد تقول «كل ما استند إليه هذا الحكم موقَّع» وهي لم
ترَ نصف ما استند إليه.

لا رقم منصوص هنا: كلها عرف بناء أو معامل محرك. لكن العرف الذي يُصدر خطأً
يُراجع كالمنصوص — والفرق أن مرجعه يُعلن أنه عرف، فلا تُنسب سلطة فقرةٍ
إلى ما لا نصّ له.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class DetailProfile:
    edition: str = "2023-01 (عرف بناء — غير مُتحقَّق)"
    verified_by: str = ""

    # ─── الفتحات: مشتركة بين الصقل والرسم ───
    door_frame_mm: int = 55
    """إطار الباب على كل جانب. يُقطع من الجدار ويُفرض كتفًا في DRW-009."""
    jamb_nib_min_mm: int = 100
    door_head_mm: int = 2040
    window_head_mm: int = 2100
    window_sill_mm: int = 900
    escape_sill_mm: int = 850
    window_corner_offset_mm: int = 400
    window_min_width_mm: int = 600

    window_openable_fraction: float = 0.5
    """
    كان عاريًا في سطر حساب في `placement.py` وثابتًا مسمّى في
    `refine.py`. **يقرّر وحده جواز تهوية ADF**: البسط في DRW-010 حاصلُ
    ضربه. افتراضُ نافذة منزلقة أو محوَّرة قياسية؛ مصراعٌ كامل يرفعه إلى
    1.0، وزجاجٌ ثابت يُنزله إلى 0.
    """

    generation_vent_ratio: float = 1 / 16
    """
    النسبة التي يُولّد بها الصقل النوافذ — أوسع من 1/20 في ADF هامشَ
    أمان، لأن المساحة الصافية أصغر من مساحة خط المركز. الرقمان مقصودان
    مختلفين: هذا للتوليد، وذاك للحكم.
    """

    # ─── الجدران ───
    structural_min_ratio: float = 0.60
    vertical_align_tol_mm: int = 60
    align_snap_mm: int = 150
    wall_sliver_min_mm: int = 150
    swing_clearance_mm: int = 100

    # ─── الرأسي ───
    stair_stack_min_overlap: float = 0.90
    wet_stack_min_overlap: float = 0.30
    """تراكب يكفي لاعتبار غرفتين رطبتين على عمود واحد. يقود GEO-011 وترتيب البدائل."""
    storage_cap_ratio: float = 0.10
    drain_run_warn_mm: int = 6000

    # ─── المطبخ ───
    kitchen_side_tol_mm: int = 400
    kitchen_min_segment_mm: int = 1000
    hob_window_proximity_mm: int = 700

    # ─── معاملات محرك: تغيّر الأحكام ولا تُوقَّع ───
    pack_grid_mm: int = 50
    """
    خطوة شبكة الحزم. ليست تفصيلة عرض: الغرفة تُقلَّص إليها، فغرفة تفشل
    بفارق 30 مم قد تنجح على شبكة أدقّ. تُصدر FIX-001 بنفسها.
    """
    line_cluster_tol_mm: int = 25
    tiling_tol_ratio: float = 0.001
    facade_tol_mm: int = 200
    stair_steps_max: int = 24
    dim_min_span_mm: int = 30


DETAIL = DetailProfile()
