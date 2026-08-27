from __future__ import annotations
from dataclasses import dataclass
from planforge.enums import Side
from planforge.units import TOL


@dataclass(frozen=True, slots=True)
class Rect:
    """مستطيل بإحداثيات ملّيمترية صحيحة. (x, y) = الزاوية الدنيا-اليسرى."""
    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(f"أبعاد غير صالحة: w={self.w}, h={self.h}")

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def min_dim(self) -> int:
        return min(self.w, self.h)

    @property
    def max_dim(self) -> int:
        return max(self.w, self.h)

    @property
    def aspect(self) -> float:
        return self.max_dim / self.min_dim

    @property
    def centroid(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def overlap_area(self, other: Rect) -> int:
        dx = min(self.x2, other.x2) - max(self.x, other.x)
        dy = min(self.y2, other.y2) - max(self.y, other.y)
        return dx * dy if dx > 0 and dy > 0 else 0

    def contains(self, other: Rect) -> bool:
        return (other.x >= self.x - TOL and other.y >= self.y - TOL
                and other.x2 <= self.x2 + TOL and other.y2 <= self.y2 + TOL)

    def shared_edge(self, other: Rect) -> tuple[int, Side | None]:
        """
        طول الحد المشترك بين مستطيلين متلاصقين، والجهة من منظور self.
        يعود (0, None) إن لم يتلاصقا. التراكب لا يُعتبر تلاصقًا.
        """
        if abs(self.x2 - other.x) <= TOL:
            length = min(self.y2, other.y2) - max(self.y, other.y)
            if length > TOL:
                return length, Side.EAST
        if abs(other.x2 - self.x) <= TOL:
            length = min(self.y2, other.y2) - max(self.y, other.y)
            if length > TOL:
                return length, Side.WEST
        if abs(self.y2 - other.y) <= TOL:
            length = min(self.x2, other.x2) - max(self.x, other.x)
            if length > TOL:
                return length, Side.NORTH
        if abs(other.y2 - self.y) <= TOL:
            length = min(self.x2, other.x2) - max(self.x, other.x)
            if length > TOL:
                return length, Side.SOUTH
        return 0, None

    def external_edges(self, envelope: Rect) -> dict[Side, int]:
        """أطوال حدود هذا المستطيل الملامسة لمحيط المظروف (واجهات خارجية)."""
        out: dict[Side, int] = {}
        if abs(self.x - envelope.x) <= TOL:
            out[Side.WEST] = self.h
        if abs(self.x2 - envelope.x2) <= TOL:
            out[Side.EAST] = self.h
        if abs(self.y - envelope.y) <= TOL:
            out[Side.SOUTH] = self.w
        if abs(self.y2 - envelope.y2) <= TOL:
            out[Side.NORTH] = self.w
        return out

    def external_perimeter(self, envelope: Rect) -> int:
        return sum(self.external_edges(envelope).values())

    def inset(self, d: int) -> Rect:
        return Rect(self.x + d, self.y + d, self.w - 2 * d, self.h - 2 * d)
