"""
خريطة الاستناد: كل مخالفة تُعلن الأرقام التي تُقرأ لإصدارها.

خريطة ثابتة مكتوبة بيد، لا استنباطًا آليًا. المقايضة صريحة: يجب تحديثها
مع كل قاعدة جديدة، واختبار في `tests/` يفشل إن نُسيت. المقابل أن كل حكم
يعرف شجرة استناده بدقّة، بلا سحر وقت التشغيل ولا تتبّع للقراءات.

النجمة `[*]` تعني «كل المسارات بهذه البادئة» — تتوسّع من السجل، فلا
تتباعد الخريطة عن الأرقام إن أُضيف نوع غرفة أو فئة وصول.

⚠ حالة التحقق: هذه الخريطة كُتبت بقراءة القواعد لا بتتبّع تنفيذها. أن
تُحلّ كل أنماطها إلى مسارات موجودة **مضمونٌ باختبار**؛ أن يكون الإسناد
صحيحًا **غير مضمون**. راجعها قاعدةً قاعدة قبل الاعتماد على كتلة الاعتماد.
"""
from __future__ import annotations
from planforge.codes.provenance import REGISTRY

RULE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    # ═══ هندسية (خطوط المراكز) ═══
    "GEO-001": (),
    "GEO-002": (),
    "GEO-003": ("detail.tiling_tol_ratio",),
    "GEO-004": ("uk.practical_min_width[*]",),
    "GEO-005": ("uk.max_aspect_default",),
    "GEO-006": (),
    "GEO-007": (),
    "GEO-008": ("uk.door_min_clear_width[*]",),
    "GEO-009": (),
    "GEO-010": ("detail.stair_stack_min_overlap",),
    "GEO-011": ("detail.wet_stack_min_overlap",),
    "GEO-012": (),
    "GEO-013": (),
    "GEO-014": (),
    "GEO-015": (),
    "GEO-016": ("uk.door_min_clear_width[*]",),
    "GEO-017": (),
    "GEO-018": (),
    "GEO-019": (),
    "GEO-020": (),

    # ═══ NDSS ═══
    "NDSS-001": ("uk.bedroom_min_area[*]",),
    "NDSS-002": ("uk.bedroom_min_width[*]",),
    "NDSS-003": ("uk.ndss_gia_table[*]",),
    "NDSS-004": ("uk.storage_by_bedrooms[*]",),
    "NDSS-005": ("uk.ceiling_min_height", "uk.ceiling_min_coverage"),
    "NDSS-006": ("uk.ndss_gia_table[*]",),

    # ═══ Part M ═══
    "ADM-001": ("uk.door_min_clear_width[*]",),
    "ADM-002": ("uk.corridor_min_width[*]",),
    "ADM-003": ("uk.wc_at_entrance_storey_required",),
    "ADM-004": ("uk.door_side_nib", "uk.door_min_clear_width[*]"),

    # ═══ Part B ═══
    "ADB-001": ("uk.protected_stair_threshold",),
    "ADB-002": (
        "uk.escape_window_min_area", "uk.escape_window_min_dim",
        "uk.escape_window_sill_range",
    ),
    "ADB-003": (
        "uk.fire_door_rating_minutes", "uk.door_min_clear_width[*]",
    ),
    "ADB-004": ("uk.alt_escape_threshold",),
    "ADB-005": ("uk.protected_stair_threshold",),
    "ADB-006": ("uk.door_min_clear_width[*]",),

    # ═══ Part F ═══
    "ADF-001": ("uk.purge_vent_ratio",),
    "ADF-002": ("uk.extract_rates_ls[*]",),

    # ═══ Part G ═══
    "ADG-001": (
        "uk.wc_needs_lobby_to_kitchen", "uk.door_min_clear_width[*]",
    ),

    # ═══ Part K ═══
    "ADK-000": (),
    "ADK-001": (
        "uk.stair_max_rise", "uk.stair_min_going", "uk.stair_2r_plus_g",
    ),
    "ADK-002": ("uk.stair_max_pitch_deg",),
    "ADK-003": ("uk.stair_min_width",),
    "ADK-004": ("uk.stair_min_headroom",),

    # ═══ ثقافية — لا رقم كوديًا ═══
    "CUL-MAJ-001": (),
    "CUL-MAJ-002": (),
    "CUL-MAJ-003": ("uk.door_min_clear_width[*]",),
    "CUL-MAJ-004": ("uk.door_min_clear_width[*]",),
    "CUL-MAJ-005": ("uk.door_min_clear_width[*]",),
    "CUL-MAJ-006": (),
    "CUL-MAJ-007": (),

    # ═══ الرسم (أبعاد صافية) ═══
    "DRW-000": ("detail.window_min_width_mm",),
    "DRW-001": ("uk.bedroom_min_area[*]",),
    "DRW-002": ("uk.bedroom_min_width[*]",),
    "DRW-003": ("uk.practical_min_width[*]",),
    "DRW-004": ("uk.corridor_min_width[*]",),
    "DRW-005": ("uk.ndss_gia_table[*]",),
    "DRW-006": ("uk.door_min_clear_width[*]",),
    "DRW-007": (
        "detail.swing_clearance_mm", "uk.door_min_clear_width[*]",
    ),
    "DRW-008": (),
    "DRW-009": ("detail.door_frame_mm",),
    "DRW-010": (
        "uk.purge_vent_ratio", "detail.window_head_mm",
        "detail.window_sill_mm", "detail.window_openable_fraction",
    ),
    "DRW-011": (
        "uk.escape_window_min_area", "detail.window_head_mm",
        "detail.escape_sill_mm", "detail.window_openable_fraction",
    ),
    "DRW-012": ("uk.escape_window_min_dim",),
    "DRW-013": ("uk.escape_window_sill_range",),
    "DRW-014": (
        "uk.fire_door_rating_minutes", "uk.protected_stair_threshold",
        "detail.structural_min_ratio",
    ),
    "DRW-015": (
        "uk.protected_stair_threshold",
        "detail.structural_min_ratio", "detail.vertical_align_tol_mm",
    ),
    "DRW-016": ("detail.wall_sliver_min_mm",),
    "DRW-017": (),
    "DRW-018": (),

    # ═══ التجهيزات ═══
    "FIX-001": (
        "fix.catalogue[*].w", "fix.catalogue[*].d",
        "fix.catalogue[*].activity_w", "fix.catalogue[*].activity_d",
        "fix.catalogue[*].against_wall",
        "fix.turning_space[*]", "fix.door_swing_clear_of_activity",
        "detail.pack_grid_mm", "uk.door_min_clear_width[*]",
    ),
    "FIX-002": ("fix.turning_space[*]",),
    "FIX-003": (
        "fix.worktop_run_by_bedspaces[*]", "fix.kitchen_gangway[*]",
        "fix.worktop_depth", "fix.worktop_height", "fix.corner_loss_mm",
        "fix.hob_to_sink_min", "fix.hob_from_corner_min",
        "fix.hob_under_window_forbidden",
        "detail.kitchen_side_tol_mm", "detail.kitchen_min_segment_mm",
        "detail.hob_window_proximity_mm",
    ),
    "FIX-004": (
        "fix.catalogue[*].needs_drain", "detail.drain_run_warn_mm",
    ),
    "FIX-005": (
        "fix.catalogue[*].activity_w", "fix.catalogue[*].activity_d",
        "detail.pack_grid_mm",
    ),

    # ═══ الجدوى (قبل التوليد) ═══
    "FEAS-001": (),
    "FEAS-002": (),
    "FEAS-003": (),
    "FEAS-004": ("uk.ndss_gia_table[*]",),
    "FEAS-005": ("uk.practical_min_width[*]",),
    "FEAS-006": ("uk.practical_min_width[*]",),
    "FEAS-007": (),
    "FEAS-008": (),
    "FEAS-009": (),
    "FEAS-010": (),
    "FEAS-011": ("uk.wc_at_entrance_storey_required",),
    "FEAS-012": ("uk.practical_min_width[*]",),

    # ═══ طبقة الصقل ═══
    "SOL-001": (
        "detail.align_snap_mm", "detail.storage_cap_ratio",
        "detail.window_corner_offset_mm", "detail.generation_vent_ratio",
        "uk.door_min_clear_width[*]", "detail.door_frame_mm",
        "detail.jamb_nib_min_mm",
    ),
}


def expand(patterns: tuple[str, ...]) -> frozenset[str]:
    """
    يوسّع الأنماط إلى مسارات فعلية.

    نمطٌ لا يُطابق شيئًا يرفع `KeyError` لا يُهمَل: خريطة تشير إلى مسار
    محذوف تُنتج شجرة استناد ناقصة، وكتلة اعتماد تقول «موقَّع» وهي لم تفحص.
    """
    known = REGISTRY.paths()
    out: set[str] = set()
    for pat in patterns:
        if "[*]" in pat:
            head, tail = pat.split("[*]", 1)
            hits = {
                p for p in known
                if p.startswith(head + "[") and p.endswith(tail)
            }
        elif pat.endswith(".*"):
            head = pat[:-2]
            hits = {p for p in known if p.startswith(head + ".")}
        elif pat in known:
            hits = {pat}
        else:
            hits = set()
        if not hits:
            raise KeyError(f"نمط لا يُطابق أي مسار في السجل: {pat}")
        out |= hits
    return frozenset(out)


def dependencies_of(rule_id: str) -> frozenset[str]:
    pats = RULE_DEPENDENCIES.get(rule_id)
    if not pats:
        return frozenset()
    return expand(pats)


def rules_using(path: str) -> tuple[str, ...]:
    """القواعد التي تستند إلى رقم معيّن — يُعرض في `codes show`."""
    return tuple(
        sorted(
            rid for rid in RULE_DEPENDENCIES
            if path in dependencies_of(rid)
        )
    )


def undeclared_rules(known: frozenset[str]) -> frozenset[str]:
    """معرّفات تُصدرها القواعد ولا تُعلن تبعياتها — اختبارٌ يمنعها."""
    return known - frozenset(RULE_DEPENDENCIES)


def orphan_declarations(known: frozenset[str]) -> frozenset[str]:
    """إعلانات لمعرّفات لم تعد أي قاعدة تُصدرها."""
    return frozenset(RULE_DEPENDENCIES) - known
