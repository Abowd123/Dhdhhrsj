"""
رموز الخروج عقد. سقوط هذا الاختبار يكسر كل دمج آلي.
"""
from __future__ import annotations
import json
import pytest
from planforge.cli import (
    EXIT_INFEASIBLE, EXIT_OK, EXIT_UNSIGNED, EXIT_USAGE, main,
)


def test_codes_audit_reports_unsigned(tmp_path, capsys):
    """
    بلا توقيعات، `codes audit` يخرج بالرمز 2 لا 0 ولا 1.

    الفصل مقصود: «لا أعرف إن كان يخالف» ليس «يخالف».
    """
    code = main([
        "--signatures", str(tmp_path / "none.json"), "codes", "audit",
    ])
    out = capsys.readouterr().out
    assert code == EXIT_UNSIGNED
    assert "بصمة الاعتماد" in out
    assert "فجوة" not in out or "لا رقم بلا سجل" in out


def test_codes_show_unknown_path_is_usage_error(tmp_path, capsys):
    code = main([
        "--signatures", str(tmp_path / "n.json"),
        "codes", "show", "uk.nope",
    ])
    assert code == EXIT_USAGE


def test_codes_show_known_path(tmp_path, capsys):
    code = main([
        "--signatures", str(tmp_path / "n.json"),
        "codes", "show", "uk.protected_stair_threshold",
    ])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "اتجاه الخطأ" in out
    assert "تستند إليه" in out


def test_worksheet_roundtrip_signs(tmp_path, capsys):
    import csv
    from planforge.codes.signing import SignatureBook, default_profiles

    sigs = tmp_path / "sigs.json"
    sheet = tmp_path / "ws.csv"
    code = main([
        "--signatures", str(sigs), "codes", "worksheet",
        "--out", str(sheet), "--limit", "3",
    ])
    assert code == EXIT_OK
    assert sheet.exists()

    with sheet.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "ورقة فارغة"
    for row in rows:
        row["verdict"] = "ok"
        row["clause_confirmed"] = "قرأتُ الفقرة"
        row["reviewer"] = "tester"
    with sheet.open("w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    code = main([
        "--signatures", str(sigs), "codes", "import",
        "--file", str(sheet),
        "--corrections", str(tmp_path / "corr.csv"),
    ])
    assert code == EXIT_OK
    book = SignatureBook.load(sigs)
    assert len(book) == len(rows)


def test_stale_worksheet_is_refused(tmp_path):
    """
    ورقة صُدِّرت قبل تعديل رقم تُرفض.

    وإلا وقّع المراجع قيمة لم يرَها — وهذا يُبطل معنى التوقيع كله.
    """
    import csv
    from planforge.codes.worksheet import export_worksheet, import_worksheet
    from planforge.codes.signing import SignatureBook
    from planforge.golden import override

    sheet = tmp_path / "ws.csv"
    export_worksheet(
        sheet, book=SignatureBook(), document="Approved Document B"
    )
    with sheet.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    target = next(
        r for r in rows if r["path"] == "uk.escape_window_min_dim"
    )
    target["verdict"] = "ok"
    target["clause_confirmed"] = "para 2.10"
    target["reviewer"] = "tester"
    with sheet.open("w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    book = SignatureBook()
    with override("uk.escape_window_min_dim", 400):
        out = import_worksheet(sheet, book=book)
    assert any(
        "تغيّرت في الكود" in p.reason for p in out.problems
    )
    assert "uk.escape_window_min_dim" not in out.signed


def test_diagnose_infeasible_brief(tmp_path, brief_dict, capsys):
    """متطلب مستحيل: التشخيص يخرج بـ3 ويسمّي السبب."""
    bad = {
        **brief_dict,
        "project_name": "impossible",
        "plot": {"width_mm": 3000, "depth_mm": 3000},
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    code = main(["diagnose", "--brief", str(path), "--fast"])
    out = capsys.readouterr().out
    assert code == EXIT_INFEASIBLE
    assert "حاجب" in out
    assert "→" in out, "لا اقتراح عددي — التشخيص غير قابل للتصرّف"


def test_missing_brief_is_usage_error(capsys):
    code = main(["check-brief", "--brief", "/nope/missing.json"])
    assert code == EXIT_USAGE
