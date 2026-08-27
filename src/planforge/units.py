"""
الوحدات: ملّيمتر عدد صحيح في كل النظام الداخلي.

لا تُستخدم الأعداد العشرية إلا عند العرض أو الإدخال البشري. السبب: منع
أخطاء التقريب التراكمية التي تظهر في CAD كفراغات وتقاطعات ميكرونية.
"""
from __future__ import annotations

MM = 1
M = 1000

# سماحية هندسية: أي فرق أصغر منها يُعتبر تلاصقًا تامًا
TOL = 2  # mm


def m(value: float) -> int:
    """متر (عشري) → ملّيمتر (صحيح)."""
    return int(round(value * 1000))


def to_m(value_mm: int) -> float:
    return value_mm / 1000.0


def m2(value_m2: float) -> int:
    """متر مربع → ملّيمتر مربع."""
    return int(round(value_m2 * 1_000_000))


def area_m2(area_mm2: int) -> float:
    return area_mm2 / 1_000_000.0


def fmt_m(value_mm: int) -> str:
    return f"{to_m(value_mm):.3f} م"


def fmt_area(area_mm2: int) -> str:
    return f"{area_m2(area_mm2):.2f} م²"
