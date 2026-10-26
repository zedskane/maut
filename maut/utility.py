"""Однокритериальные функции полезности, построенные по лотереям.

Кривая начинается с двух известных точек: U(худшее) = 0, U(лучшее) = 1.
Лотерея «с вероятностью 0,5 — значение a, с вероятностью 0,5 — значение b»
имеет ожидаемую полезность (U(a) + U(b)) / 2, поэтому её эквивалент
определённости (CE) получает именно эту полезность. Лотереи проводятся по
уровням: сначала между худшим и лучшим (U = 0,5), затем между найденными
точками (0,25 и 0,75) и т. д. При levels уровнях получается 2**levels + 1
точка: 3, 5, 9, 17. Между точками кривая линейная.
"""

from __future__ import annotations

import numpy as np

from .model import Criterion, MautError

LEVELS_BY_POINTS = {3: 1, 5: 2, 9: 3, 17: 4}


def points_for_levels(levels: int) -> int:
    return 2 ** levels + 1


def levels_for_points(points: int) -> int:
    if points not in LEVELS_BY_POINTS:
        raise MautError("Число точек кривой: 3, 5, 9 или 17")
    return LEVELS_BY_POINTS[points]


def lottery_plan(levels: int) -> list[tuple[float, float, float]]:
    """Лотереи в порядке проведения: (U левого исхода, U правого, U эквивалента).

    levels = 2 → [(0, 1, 0.5), (0, 0.5, 0.25), (0.5, 1, 0.75)].
    """
    if levels < 1:
        raise MautError("Нужен хотя бы один уровень лотерей")
    plan = []
    for d in range(levels):
        n = 2 ** d
        for k in range(n):
            lo, hi = k / n, (k + 1) / n
            plan.append((lo, hi, (lo + hi) / 2))
    return plan


def ukey(u: float) -> str:
    """Ключ полезности для словарей и JSON: 0.25 → «0.25»."""
    return f"{u:.6g}"


class UtilityFunction:
    """Кусочно-линейная функция полезности по точкам (x, U).

    Значения вне диапазона [худшее, лучшее] прижимаются к границам: U ∈ [0, 1].
    """

    def __init__(self, criterion: Criterion, points: list[tuple[float, float]]):
        self.criterion = criterion
        pts = sorted(points, key=lambda p: p[1])
        ts = [criterion.t(x) for x, _ in pts]
        us = [u for _, u in pts]
        if any(b <= a for a, b in zip(ts, ts[1:])):
            raise MautError(
                f"«{criterion.name}»: точки кривой полезности не монотонны — "
                "более полезная точка должна быть ближе к наилучшему значению"
            )
        if abs(us[0]) > 1e-12 or abs(us[-1] - 1) > 1e-12:
            raise MautError(f"«{criterion.name}»: кривая должна начинаться в 0 и заканчиваться в 1")
        self.points = pts
        self._t = np.array(ts)
        self._u = np.array(us)

    def __call__(self, x):
        t = np.clip(self.criterion.t(np.asarray(x, dtype=float)), 0.0, 1.0)
        u = np.interp(t, self._t, self._u)
        return float(u) if np.ndim(u) == 0 else u

    def inverse(self, u: float) -> float:
        """Значение критерия с заданной полезностью."""
        t = float(np.interp(np.clip(u, 0, 1), self._u, self._t))
        return self.criterion.x(t)
