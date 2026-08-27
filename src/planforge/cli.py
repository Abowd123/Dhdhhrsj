"""
سطر الأوامر.

رموز الخروج **عقد**، لا تفصيلة عرض: بلا تعريف ثابت لا يُدمج شيء في CI.
  0 — سليم
  1 — مخالفات
  2 — أرقام غير موقَّعة أو فجوة في سجل الإثبات
  3 — تعذّر (لا حل)
  4 — خطأ استخدام أو ملف

الفصل بين 1 و2 مقصود: `1` يقول «المخطط يخالف»، و`2` يقول «لا أعرف إن
كان يخالف لأن أرقامي غير مُصدَّقة». الأول قرار تصميم، والثاني قرار
اعتماد، وخلطهما يجعل البوابة عقبةً تُتجاوَز.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from planforge.assurance import Assurance, annotate, assess
from planforge.codes.provenance import REGISTRY, coverage
from planforge.codes.signing import (
    DEFAULT_PATH, SignatureBook, default_profiles,
)
from planforge.codes.usage import rules_using
from planforge.codes.worksheet import (
    export_worksheet, import_worksheet, progress, write_corrections,
)
from planforge.model.brief import Brief
from planforge.pipeline import Result, closest, run as run_pipeline
from planforge.project import Project
from planforge.ranking import RankWeights, record_choice
from planforge.rules.brief_rules import check_brief
from planforge.rules.core import ComplianceReport
from planforge.solver.config import SolverConfig
from planforge.solver.diagnose import diagnose
from planforge.units import area_m2

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_UNSIGNED = 2
EXIT_INFEASIBLE = 3
EXIT_USAGE = 4


# ═══════════════ طباعة ═══════════════

def _p(text: str = "") -> None:
    print(text)


def print_report(rep: ComplianceReport, title: str) -> None:
    head = "✓" if rep.ok else "✗"
    _p(
        f"\n{head} {title} — {len(rep.errors)} مخالفة، "
        f"{len(rep.warnings)} تحذير، "
        f"{len(set(rep.rules_run))} معرّفًا فُحص"
    )
    for v in rep.errors:
        where = f" [دور {v.storey}]" if v.storey is not None else ""
        rooms = f" ({', '.join(v.rooms)})" if v.rooms else ""
        _p(f"  ✗ {v.rule_id}{where}{rooms} {v.message}")
        if v.actual or v.required:
            _p(f"      المقيس {v.actual} · المطلوب {v.required}")
        _p(f"      المرجع: {v.reference}")
    for v in rep.warnings:
        rooms = f" ({', '.join(v.rooms)})" if v.rooms else ""
        _p(f"  ! {v.rule_id}{rooms} {v.message}")


def print_assurance(a: Assurance) -> None:
    _p(f"\n── الاعتماد ──\n{a.summary_ar()}")
    if a.permissive_unsigned:
        _p("\nأرقام غير موقَّعة خطؤها يميل إلى التسامح (ابدأ منها):")
        for v in a.permissive_unsigned[:12]:
            _p(f"  · {v.path} = {v.current}   {v.reference}")
        extra = len(a.permissive_unsigned) - 12
        if extra > 0:
            _p(f"  … و{extra} غيرها")
    _p(f"\n{a.stamp()}")


def _load_brief(path: Path) -> Brief:
    return Brief.model_validate_json(path.read_text(encoding="utf-8"))


def _book(args) -> SignatureBook:
    return SignatureBook.load(Path(args.signatures))


def _gate(a: Assurance, require_signed: bool) -> int:
    return (
        EXIT_UNSIGNED
        if require_signed and not a.delivery_ready
        else EXIT_OK
    )


# ═══════════════ الأوامر ═══════════════

def cmd_check_brief(args) -> int:
    brief = _load_brief(Path(args.brief))
    rep = check_brief(brief, SolverConfig())
    print_report(rep, "جدوى المتطلب")
    return EXIT_OK if rep.ok else EXIT_VIOLATIONS


def cmd_diagnose(args) -> int:
    brief = _load_brief(Path(args.brief))
    dx = diagnose(
        brief, SolverConfig(time_limit_s=args.time_limit),
        run_solver=not args.fast,
    )
    _p(f"\n── تشخيص «{brief.project_name}» ──")
    for sev, label in (
        ("blocking", "حاجب"), ("likely", "مرجَّح"), ("note", "ملاحظة")
    ):
        rows = [f for f in dx.findings if f.severity == sev]
        if not rows:
            continue
        _p(f"\n{label}:")
        for f in rows:
            _p(f"  {f.line()}")
            if f.suggestion:
                _p(f"      → {f.suggestion}")
    if dx.binding:
        _p("\nالقيود المُلزِمة:")
        for storey, rung in sorted(dx.binding.items()):
            _p(f"  دور {storey}: {rung}")
    if dx.unresolved:
        _p(f"\nأدوار متعذّرة حتى بكل الإرخاء: {list(dx.unresolved)}")
    if dx.ok:
        _p("\n✓ لا مانع — المتطلب قابل للحل.")
        return EXIT_OK
    return EXIT_INFEASIBLE


def cmd_run(args) -> int:
    brief = _load_brief(Path(args.brief))
    cfg = SolverConfig(
        seed=args.seed if args.seed is not None else brief.seed,
        n_alternatives=args.alternatives,
        time_limit_s=args.time_limit,
        deterministic=args.deterministic,
    )
    weights = RankWeights.load(
        Path(args.weights) if args.weights else None
    )
    best, feas, attempted = run_pipeline(
        brief, cfg, weights=weights, skip_fixtures=args.no_fixtures
    )

    print_report(feas, "جدوى المتطلب")
    if not feas.ok:
        _p("\nالمتطلب غير مُجدٍ — لم يُشغَّل المُحلّل.")
        return EXIT_VIOLATIONS

    fallback = best is None
    result = best or closest(attempted)
    if result is None:
        _p("\n✗ لم يُنتج المُحلّل أي بديل.")
        _p("  شغّل: planforge diagnose --brief …")
        return EXIT_INFEASIBLE

    if fallback:
        _p(
            f"\n⚠ لم يجُز أي بديل من {len(attempted)}. "
            f"يُعرض أقربها ({result.total_errors} مخالفة)."
        )

    _p(
        f"\nدورات {result.rounds} · انكماش الجدران "
        f"{1 - result.shrink_ratio:.1%} · بدائل مفحوصة {len(attempted)} · "
        f"الدرجة {result.rank}"
    )
    if result.shrink_notes:
        _p("\nغرف انكمشت دون مستهدفها (ارفع المستهدف في المتطلب):")
        for note in result.shrink_notes[:8]:
            _p(f"  · {note}")
    _p(f"مسار المُحلّل: {cfg.limits().describe()}")
    if not args.deterministic:
        _p(
            "  ⚠ غير حتمي: نفس المتطلب قد يُنتج مخططًا مختلفًا. "
            "استخدم --deterministic إن أردت replay موثوقًا."
        )
    _p(
        f"المساحة الصافية "
        f"{area_m2(result.drawing.total_gia_mm2):.2f} م²"
    )
    print_report(result.layout_report, "خطوط المراكز")
    print_report(result.drawing_report, "الأبعاد الصافية")
    print_report(result.fixture_report, "قابلية التأثيث")

    book = _book(args)
    a = assess(
        [
            result.layout_report, result.drawing_report,
            result.fixture_report, feas,
        ],
        book=book,
    )
    print_assurance(a)

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    proj = Project(
        engine_version=result.layout.engine_version,
        brief=brief, layout=result.layout,
        deterministic=args.deterministic,
    )
    saved = proj.save(out / f"{brief.project_name}.pfproj.json")
    _p(f"\nحُفظ: {saved}")

    if args.svg:
        from planforge.export.svg import drawing_svg
        html = drawing_svg(
            result.drawing,
            unfurnishable=frozenset(result.fixtures.unfurnishable),
            stamp=a.stamp(),
        )
        path = out / f"{brief.project_name}.svg.html"
        path.write_text(
            f"<!DOCTYPE html><html lang='ar' dir='rtl'>"
            f"<meta charset='utf-8'><body>{html}</body></html>",
            encoding="utf-8",
        )
        _p(f"حُفظ: {path}")

    if args.dxf:
        from planforge.export.dxf import export_dxf
        path, counts = export_dxf(
            result.drawing, out / f"{brief.project_name}.dxf",
            stamp=a.stamp(), arabic_labels=not args.latin_labels,
        )
        _p(
            f"حُفظ: {path} ({counts['storeys']} دور، "
            f"{counts['walls']} جدارًا، {counts['openings']} فتحة)"
        )
        if args.latin_labels:
            _p("  المسميات لاتينية — مضمونة في كل العارضات.")
        else:
            _p(
                "  المسميات عربية: تشكيل الحروف يجري في برنامج العرض. "
                "استخدم --latin-labels لمخرج مضمون."
            )

    if args.json:
        payload = {
            "project": brief.project_name,
            "ok": result.ok,
            "rank": result.rank,
            "rounds": result.rounds,
            "features": result.features.__dict__,
            "assurance": a.to_dict(),
            "shrink_ratio": result.shrink_ratio,
            "shrink_notes": result.shrink_notes,
            "violations": annotate(result.layout_report, book)
            + annotate(result.drawing_report, book)
            + annotate(result.fixture_report, book),
        }
        path = out / f"{brief.project_name}.report.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _p(f"حُفظ: {path}")

    gate = _gate(a, args.require_signed)
    if gate:
        return gate
    return EXIT_OK if result.ok else EXIT_VIOLATIONS


def cmd_replay(args) -> int:
    proj = Project.load(Path(args.project))
    session, failures = proj.replay(skip_fixtures=args.no_fixtures)
    _p(
        f"\nإعادة تشغيل {len(proj.history)} عملية على "
        f"«{proj.brief.project_name}»"
    )
    if not proj.deterministic:
        _p(
            "\n⚠ الملف وُلِّد بالمسار غير الحتمي — الفروق أدناه قد تكون من "
            "المُحلّل لا من تغيّر الأرقام."
        )
    if failures:
        _p(f"\n✗ {len(failures)} عملية لم تُطبَّق:")
        for line in failures:
            _p(f"  {line}")
        _p(
            "\nالملف لم يبقَ قابلًا لإعادة الإنتاج: تغيّر إصدار المحرك أو "
            "رقم كودي منذ الحفظ."
        )
    for rep, title in (
        (session.state.layout_report, "خطوط المراكز"),
        (session.state.drawing_report, "الأبعاد الصافية"),
        (session.state.fixture_report, "قابلية التأثيث"),
    ):
        print_report(rep, title)
    if failures:
        return EXIT_VIOLATIONS
    return EXIT_OK if session.state.ok else EXIT_VIOLATIONS


def cmd_serve(args) -> int:
    from planforge.server.app import serve
    serve(
        host=args.host, port=args.port,
        signatures=Path(args.signatures),
        allow_public=args.allow_public,
        skip_fixtures=args.no_fixtures,
    )
    return EXIT_OK


# ─────────── الأرقام ───────────

def cmd_codes_audit(args) -> int:
    profiles = default_profiles()
    gaps, total = coverage(profiles)
    book = _book(args)
    tally = book.tally(profiles)

    _p(f"\n── سجل الإثبات ──\n{total} قيمة، {len(REGISTRY.paths())} سجلًّا")
    if gaps:
        _p(f"\n✗ {len(gaps)} فجوة تغطية — عيبٌ برمجي لا دَين مراجعة:")
        for g in gaps[:25]:
            _p(f"  {g.path} — {g.reason}")
        extra = len(gaps) - 25
        if extra > 0:
            _p(f"  … و{extra} غيرها")
    else:
        _p("✓ لا رقم بلا سجل، ولا سجل بلا رقم.")

    _p(
        f"\nموقَّع {tally['signed']} · بطل توقيعه {tally['stale']} · "
        f"غير موقَّع {tally['unsigned']} · "
        f"لا يحتاج {tally['not_required']}"
    )
    _p(f"بصمة الاعتماد: {book.fingerprint(profiles)}")

    risky = REGISTRY.high_risk()
    if risky:
        _p(f"\nأعلى خطرًا ({len(risky)}): من الذاكرة + خطؤه متسامح")
        for prov in risky[:15]:
            _p(f"  · {prov.path} — {prov.ref.label() if prov.ref else '—'}")

    if gaps:
        return EXIT_UNSIGNED
    if tally["unsigned"] or tally["stale"]:
        return EXIT_UNSIGNED
    return EXIT_OK


def cmd_codes_show(args) -> int:
    prov = REGISTRY.get(args.path)
    if prov is None:
        _p(f"لا سجل للمسار: {args.path}")
        return EXIT_USAGE
    from planforge.codes.provenance import values_of
    value = values_of(default_profiles()).get(args.path)
    st = _book(args).status_of(args.path, value)
    users = rules_using(args.path)
    _p(f"\n{prov.path}")
    _p(f"  القيمة        {value!r} ({prov.unit})")
    _p(f"  الثقة         {prov.confidence}")
    _p(f"  اتجاه الخطأ   {prov.safety_direction}")
    _p(f"  المرجع        {prov.ref.label() if prov.ref else '—'}")
    _p(f"  الحالة        {st.state}")
    if st.signature:
        _p(
            f"  وقّعه         {st.signature.signed_by} "
            f"في {st.signature.signed_on}"
        )
        _p(f"  الفقرة        {st.signature.clause_confirmed}")
    if prov.note:
        _p(f"  ملاحظة        {prov.note}")
    _p(f"  تستند إليه    {len(users)} قاعدة: {', '.join(users) or '—'}")
    return EXIT_OK


def cmd_codes_worksheet(args) -> int:
    path, count = export_worksheet(
        Path(args.out), book=_book(args), document=args.document,
        confidence=args.confidence, include_signed=args.include_signed,
        limit=args.limit,
    )
    _p(f"\nصُدِّرت ورقة بـ{count} صفًّا: {path}")
    _p(
        "املأ verdict (ok/wrong)، و clause_confirmed، و reviewer. "
        "ثم: planforge codes import --file …"
    )
    return EXIT_OK if count else EXIT_OK


def cmd_codes_import(args) -> int:
    book = _book(args)
    out = import_worksheet(Path(args.file), book=book)
    if out.problems:
        _p(f"\n✗ {len(out.problems)} صفًّا مرفوضًا:")
        for pr in out.problems:
            _p(f"  {pr.path} — {pr.reason}")
    _p(
        f"\nوُقِّع {len(out.signed)} · تصحيحات مطلوبة "
        f"{len(out.corrections)} · مؤجَّل {out.skipped}"
    )
    if out.signed:
        book.save(Path(args.signatures))
        _p(f"حُفظت التوقيعات: {args.signatures}")
    corr = write_corrections(out, Path(args.corrections))
    if corr:
        _p(f"التصحيحات المطلوبة: {corr}")
        _p("قِس أثر كل تصحيح قبل تطبيقه — الأمر في العمود الأخير.")
    return EXIT_USAGE if out.problems else EXIT_OK


def cmd_codes_progress(args) -> int:
    data = progress(_book(args))
    _p(f"\nحتى {data['as_of']} · بصمة {data['fingerprint']}")
    for doc, counts in sorted(data["by_document"].items()):
        total = sum(counts.values())
        done = counts["signed"]
        bar = "█" * int(20 * done / total) if total else ""
        _p(
            f"  {done:3}/{total:3} {bar:<20} {doc}"
            f"{' · بطل ' + str(counts['stale']) if counts['stale'] else ''}"
        )
    return EXIT_OK


def cmd_codes_impact(args) -> int:
    from planforge.golden import compare_with_override
    try:
        value = json.loads(args.value)
    except json.JSONDecodeError:
        value = args.value
    flips = compare_with_override(
        Path(args.golden), args.path, value,
        skip_fixtures=not args.with_fixtures,
    )
    _p(f"\nلو صار {args.path} = {value!r}:")
    if not flips:
        _p("  لا حكم ينقلب في الحالات المرجعية.")
        _p(
            "  ⚠ لا يعني أن التغيير آمن — يعني أن حالاتك المرجعية لا "
            "تلمسه. أضِف حالة تلمسه."
        )
        return EXIT_OK
    for f in flips:
        _p(f"  {f['case']} · {f['rule']}: {f['before']} → {f['after']}")
    return EXIT_OK


def cmd_golden(args) -> int:
    from planforge.golden import run_all
    results = run_all(
        Path(args.dir), skip_fixtures=not args.with_fixtures
    )
    if not results:
        _p(f"لا حالات في {args.dir}")
        return EXIT_USAGE
    bad = [r for r in results if not r.ok]
    for r in results:
        mark = "✓" if r.ok else "✗"
        _p(f"{mark} {r.name} [{r.source}]")
        if r.missing:
            _p(f"    توقّعنا ولم تظهر: {sorted(r.missing)}")
        if r.unexpected:
            _p(f"    ظهرت ولم نتوقّعها: {sorted(r.unexpected)}")
    synthetic = sum(1 for r in results if r.source == "synthetic")
    _p(
        f"\n{len(results) - len(bad)}/{len(results)} حالة مطابقة للتوقّع"
    )
    if synthetic:
        _p(
            f"⚠ {synthetic} حالة تركيبية — تحمي من الانحدار ولا تصدّق "
            f"رقمًا. استبدلها بمخططات معتمدة فعلًا."
        )
    return EXIT_VIOLATIONS if bad else EXIT_OK


def cmd_choose(args) -> int:
    """
    عرض البدائل وتسجيل الاختيار.

    كل اختيار تفضيلات زوجية تُخزَّن محليًا. بعد بضع مئات تُدرَّب أوزان
    على قرارات هذا المهندس — بلا لمس أي قيد صلب.
    """
    brief = _load_brief(Path(args.brief))
    cfg = SolverConfig(
        seed=brief.seed, n_alternatives=args.alternatives,
        time_limit_s=args.time_limit,
    )
    _best, _feas, attempted = run_pipeline(
        brief, cfg, skip_fixtures=args.no_fixtures
    )
    if not attempted:
        _p("لا بدائل.")
        return EXIT_INFEASIBLE
    ranked: list[Result] = sorted(
        attempted, key=lambda r: (r.total_errors, -r.rank)
    )
    for i, r in enumerate(ranked):
        _p(
            f"[{i}] الدرجة {r.rank:9.1f} · {r.total_errors} مخالفة · "
            f"{r.total_warnings} تحذير · "
            f"حركة {r.features.circulation_ratio:.1%} · "
            f"صافٍ {area_m2(r.drawing.total_gia_mm2):.1f} م²"
        )
    if args.pick is None:
        _p("\nأعِد الأمر مع --pick N لتسجيل الاختيار.")
        return EXIT_OK
    path = record_choice(
        Path(args.out).expanduser(), args.pick,
        [r.features for r in ranked], brief.project_name,
    )
    _p(f"\nسُجِّل الاختيار في {path}")
    return EXIT_OK


# ═══════════════ التركيب ═══════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="planforge",
        description=(
            "توليد مخططات سكنية مُدقَّقة. المخرجات تُختم "
            "NOT FOR CONSTRUCTION حتى تُوقَّع الأرقام الكودية."
        ),
    )
    p.add_argument(
        "--signatures", default=str(DEFAULT_PATH),
        help="ملف توقيعات الأرقام",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_brief(sp):
        sp.add_argument("--brief", required=True)
        sp.add_argument("--no-fixtures", action="store_true")

    sp = sub.add_parser("check-brief", help="فحص جدوى سريع")
    sp.add_argument("--brief", required=True)
    sp.set_defaults(fn=cmd_check_brief)

    sp = sub.add_parser("diagnose", help="لماذا تعذّر الحل")
    sp.add_argument("--brief", required=True)
    sp.add_argument("--fast", action="store_true", help="بلا سُلَّم الإرخاء")
    sp.add_argument("--time-limit", type=float, default=20.0)
    sp.set_defaults(fn=cmd_diagnose)

    sp = sub.add_parser("run", help="توليد وتدقيق وحفظ")
    add_brief(sp)
    sp.add_argument("--out", default="out")
    sp.add_argument("--seed", type=int)
    sp.add_argument("--alternatives", type=int, default=6)
    sp.add_argument("--time-limit", type=float, default=20.0)
    sp.add_argument("--weights")
    sp.add_argument("--svg", action="store_true")
    sp.add_argument("--dxf", action="store_true", help="تصدير DXF للتسليم")
    sp.add_argument(
        "--latin-labels", action="store_true",
        help="مسميات لاتينية في DXF — مخرج مضمون في كل العارضات",
    )
    sp.add_argument("--json", action="store_true")
    sp.add_argument(
        "--require-signed", action="store_true",
        help="اخرج بالرمز 2 إن استند حكم إلى رقم غير موقَّع",
    )
    sp.add_argument(
        "--deterministic", action="store_true",
        help="مسار حتمي (أبطأ 3–6×) — لازم لإعادة الإنتاج و replay",
    )
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("replay", help="إعادة تشغيل سجل مشروع")
    sp.add_argument("--project", required=True)
    sp.add_argument("--no-fixtures", action="store_true")
    sp.set_defaults(fn=cmd_replay)

    sp = sub.add_parser("serve", help="خادم المحرر (بلا مصادقة)")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.add_argument("--allow-public", action="store_true")
    sp.add_argument("--no-fixtures", action="store_true")
    sp.set_defaults(fn=cmd_serve)

    sp = sub.add_parser("choose", help="عرض البدائل وتسجيل الاختيار")
    add_brief(sp)
    sp.add_argument("--alternatives", type=int, default=6)
    sp.add_argument("--time-limit", type=float, default=20.0)
    sp.add_argument("--pick", type=int)
    sp.add_argument("--out", default=".")
    sp.set_defaults(fn=cmd_choose)

    sp = sub.add_parser("golden", help="تشغيل الحالات المرجعية")
    sp.add_argument("--dir", default="tests/golden")
    sp.add_argument("--with-fixtures", action="store_true")
    sp.set_defaults(fn=cmd_golden)

    codes = sub.add_parser("codes", help="إدارة الأرقام الكودية")
    csub = codes.add_subparsers(dest="sub", required=True)

    s = csub.add_parser("audit", help="تغطية السجل وحالة التوقيع")
    s.set_defaults(fn=cmd_codes_audit)

    s = csub.add_parser("show", help="تفصيل رقم واحد")
    s.add_argument("path")
    s.set_defaults(fn=cmd_codes_show)

    s = csub.add_parser("worksheet", help="تصدير ورقة مراجعة")
    s.add_argument("--out", default="code_review.csv")
    s.add_argument("-d", "--document")
    s.add_argument("--confidence")
    s.add_argument("--include-signed", action="store_true")
    s.add_argument("--limit", type=int)
    s.set_defaults(fn=cmd_codes_worksheet)

    s = csub.add_parser("import", help="استيراد ورقة معبَّأة")
    s.add_argument("--file", required=True)
    s.add_argument("--corrections", default="code_corrections.csv")
    s.set_defaults(fn=cmd_codes_import)

    s = csub.add_parser("progress", help="تقدّم المراجعة بحسب الوثيقة")
    s.set_defaults(fn=cmd_codes_progress)

    s = csub.add_parser("impact", help="أثر تغيير رقم على الحالات المرجعية")
    s.add_argument("path")
    s.add_argument("value")
    s.add_argument("--golden", default="tests/golden")
    s.add_argument("--with-fixtures", action="store_true")
    s.set_defaults(fn=cmd_codes_impact)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except FileNotFoundError as exc:
        _p(f"ملف غير موجود: {exc}")
        return EXIT_USAGE
    except (ValueError, KeyError) as exc:
        _p(f"خطأ: {exc}")
        return EXIT_USAGE
    except KeyboardInterrupt:
        _p("\nأُلغي.")
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
