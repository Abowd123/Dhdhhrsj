from __future__ import annotations
from dataclasses import dataclass
from math import atan2, ceil, degrees
from planforge.geometry.rect import Rect


@dataclass(frozen=True, slots=True)
class StairSolution:
    n_risers: int
    rise_mm: float
    going_mm: int
    pitch_deg: float
    flight_length_mm: int
    fits: bool
    note: str = ""


def solve_straight_flight(
    floor_to_floor_mm: int,
    rect: Rect,
    *,
    max_rise_mm: int,
    min_going_mm: int,
    max_pitch_deg: float,
    twice_rise_plus_going: tuple[int, int],
    min_width_mm: int,
    landing_factor: float = 1.0,
) -> StairSolution:
    """
    يحل رحلة سلّم مستقيمة داخل مستطيل معطى ويفحصها مقابل قيود ADK.

    البسطة عند القمة تُحسب بطول = عرض السلّم (ADK: البسطة ≥ عرض السلّم).
    """
    n = ceil(floor_to_floor_mm / max_rise_mm)
    rise = floor_to_floor_mm / n
    run_available = rect.max_dim
    width_available = rect.min_dim

    # الرحلة تحتوي n-1 نائمة، زائد بسطة بطول عرض السلّم
    landing = int(width_available * landing_factor)
    going = (run_available - landing) // max(1, n - 1)
    flight_len = (n - 1) * going + landing
    pitch = degrees(atan2(rise, going)) if going > 0 else 90.0
    two_r_g = 2 * rise + going

    problems: list[str] = []
    if going < min_going_mm:
        problems.append(f"النائمة {going} < {min_going_mm}")
    if pitch > max_pitch_deg:
        problems.append(f"الميل {pitch:.1f}° > {max_pitch_deg}°")
    if not (twice_rise_plus_going[0] <= two_r_g <= twice_rise_plus_going[1]):
        problems.append(f"2R+G = {two_r_g:.0f} خارج {twice_rise_plus_going}")
    if width_available < min_width_mm:
        problems.append(f"العرض {width_available} < {min_width_mm}")
    if flight_len > run_available:
        problems.append(f"الطول المطلوب {flight_len} > المتاح {run_available}")

    return StairSolution(
        n_risers=n,
        rise_mm=rise,
        going_mm=max(going, 0),
        pitch_deg=pitch,
        flight_length_mm=flight_len,
        fits=not problems,
        note="؛ ".join(problems),
    )
