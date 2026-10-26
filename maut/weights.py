"""Веса критериев и коэффициент k мультипликативной модели.

Отношение весов двух критериев a и b находится по точке безразличия на
плоскости (a, b). Сначала ЛПР сравнивает два угловых варианта:

    A = (a — наилучшее, b — наихудшее),   B = (a — наихудшее, b — наилучшее).

Если A лучше, критерий a важнее, и ищется x на шкале a, при котором
(x, b худшее) ~ (a худшее, b лучшее). Подстановка в аддитивную функцию даёт
wa·Ua(x) + wb·0 = wa·0 + wb·1, то есть wb = wa·Ua(x).
Если лучше B, ищется y на шкале b: (a худшее, y) ~ (a лучшее, b худшее),
откуда wa = wb·Ub(y). Если A и B равноценны, wa = wb.

Прочие критерии в этих вопросах фиксируются на наихудших значениях: тогда то
же равенство верно и для мультипликативной модели (их множители равны 1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .elicitation import Record
from .model import MautError

CORNERS = ("a", "b", "equal")


@dataclass
class PairAnswer:
    """Ответы ЛПР по паре критериев (a, b).

    context — на каком уровне зафиксированы прочие критерии: «worst» или «best»;
    corner — какой угловой вариант лучше: «a», «b» или «equal»;
    record — найденная точка безразличия (на шкале a при corner = «a»,
    на шкале b при corner = «b», None при «equal»).
    """

    a: str
    b: str
    context: str
    corner: str
    record: Record | None = None

    def validate(self) -> None:
        if self.corner not in CORNERS:
            raise MautError(f"Неизвестный ответ при сравнении угловых вариантов: {self.corner}")
        if self.corner != "equal" and self.record is None:
            raise MautError(f"Пара «{self.a}» — «{self.b}»: точка безразличия не найдена")

    @property
    def scale(self) -> str | None:
        """На шкале какого критерия ищется точка безразличия."""
        return {"a": self.a, "b": self.b}.get(self.corner)

    def ratio(self, utilities) -> float:
        """Отношение wb / wa. utilities — словарь «критерий → UtilityFunction»."""
        self.validate()
        if self.corner == "equal":
            return 1.0
        u = utilities[self.scale](self.record.value)
        if u <= 0:
            raise MautError(
                f"Пара «{self.a}» — «{self.b}»: точка безразличия имеет нулевую полезность, "
                "вес получается нулевым. Проверьте ответы."
            )
        return u if self.corner == "a" else 1.0 / u

    def to_dict(self) -> dict:
        d = {"a": self.a, "b": self.b, "context": self.context, "corner": self.corner}
        if self.record is not None:
            d["record"] = self.record.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "PairAnswer":
        rec = Record.from_dict(d["record"]) if d.get("record") else None
        return PairAnswer(d["a"], d["b"], d.get("context", "worst"), d["corner"], rec)


def normalize(ratios: dict[str, float], ref: str) -> dict[str, float]:
    """Веса по отношениям wj / w_ref, нормированные к сумме 1."""
    total = 1.0 + sum(ratios.values())
    w = {ref: 1.0 / total}
    for name, r in ratios.items():
        w[name] = r / total
    return w


def solve_k(ks: list[float], tol: float = 1e-12) -> float:
    """Коэффициент k из уравнения 1 + k = Π(1 + k·ki).

    Если Σki = 1, k = 0 (модель аддитивная). Если Σki > 1, корень в (−1, 0);
    если Σki < 1 — в (0, +∞). Корень k = 0 есть всегда, поэтому ищется
    второй, ненулевой.
    """
    if not ks:
        raise MautError("Нет коэффициентов")
    if any(not (0 < k < 1) for k in ks):
        raise MautError("Коэффициенты ki мультипликативной модели должны быть в интервале (0, 1)")
    s = sum(ks)
    if abs(s - 1) < 1e-9:
        return 0.0
    if len(ks) == 1:
        raise MautError("Для одного критерия коэффициент должен быть равен 1")

    def f(k: float) -> float:
        return math.prod(1 + k * ki for ki in ks) - (1 + k)

    if s > 1:
        lo, hi = -1 + 1e-15, -1e-12
    else:
        lo, hi = 1e-12, 1.0
        while f(hi) <= 0:
            hi *= 2
            if hi > 1e12:
                raise MautError("Не удалось найти k: проверьте коэффициенты")
    flo = f(lo)
    for _ in range(300):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
        if hi - lo < tol * max(1.0, abs(mid)):
            break
    return (lo + hi) / 2


def multiplicative(ks: list[float], k: float, us: list[float]) -> float:
    """U = (Π(1 + k·ki·Ui) − 1) / k; при k = 0 — сумма ki·Ui."""
    if k == 0:
        return sum(ki * ui for ki, ui in zip(ks, us))
    return (math.prod(1 + k * ki * ui for ki, ui in zip(ks, us)) - 1) / k
