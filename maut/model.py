"""Критерии и альтернативы."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class MautError(ValueError):
    """Ошибка во входных данных или в порядке шагов метода.

    Текст сообщения показывается пользователю как есть, поэтому он на русском
    и объясняет, что исправить.
    """


@dataclass
class Criterion:
    """Критерий с диапазоном оценок от наихудшей до наилучшей.

    Наилучшее значение может быть меньше наихудшего (стоимость, время):
    направление определяется только этими двумя числами.
    """

    name: str
    unit: str
    worst: float
    best: float

    def validate(self) -> None:
        if not self.name.strip():
            raise MautError("У критерия должно быть название")
        for label, v in (("наихудшее", self.worst), ("наилучшее", self.best)):
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise MautError(f"«{self.name}»: {label} значение должно быть числом")
        if self.worst == self.best:
            raise MautError(f"«{self.name}»: наихудшее и наилучшее значения совпадают")

    @property
    def span(self) -> float:
        """Ширина диапазона, всегда положительная."""
        return abs(self.best - self.worst)

    @property
    def direction(self) -> str:
        return "max" if self.best > self.worst else "min"

    def t(self, x: float) -> float:
        """Доля пути от наихудшего значения к наилучшему (0 — худшее, 1 — лучшее)."""
        return (x - self.worst) / (self.best - self.worst)

    def x(self, t: float) -> float:
        """Обратное к t(): значение критерия по доле пути."""
        return self.worst + t * (self.best - self.worst)

    def is_between(self, x: float, a: float, b: float) -> bool:
        """x строго между a и b (в любом порядке)."""
        lo, hi = min(a, b), max(a, b)
        return lo < x < hi

    def to_dict(self) -> dict:
        return {"name": self.name, "unit": self.unit, "worst": self.worst, "best": self.best}

    @staticmethod
    def from_dict(d: dict) -> "Criterion":
        return Criterion(d["name"], d.get("unit", ""), float(d["worst"]), float(d["best"]))


@dataclass
class Alternative:
    """Альтернатива: название и оценка по каждому критерию."""

    name: str
    values: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "values": dict(self.values)}

    @staticmethod
    def from_dict(d: dict) -> "Alternative":
        return Alternative(d["name"], {k: float(v) for k, v in d["values"].items()})


def decimals(span: float) -> int:
    """Сколько знаков после запятой показывать для диапазона такой ширины."""
    if span <= 0:
        span = 1.0
    return max(0, 2 - int(math.floor(math.log10(span))))


def quantum(span: float) -> float:
    """Шаг, до которого округляются значения в вопросах (последний показанный знак)."""
    return 10.0 ** -decimals(span)


def fmt(x: float, span: float = 1.0) -> str:
    """Число с точностью, разумной для диапазона: 200 → «185», 1 → «0,63»."""
    s = f"{x:.{decimals(span)}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    return s.replace(".", ",")
