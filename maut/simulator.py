"""Модельный ЛПР для тестов и экспериментов.

У модельного ЛПР есть «истинная» функция полезности V над долями t ∈ [0, 1]
по каждому критерию (0 — наихудшее значение, 1 — наилучшее), V(все худшие) = 0,
V(все лучшие) = 1. Он отвечает на те же вопросы, что и живой ЛПР в окне:

* при прямом вводе называет эквивалент или точку безразличия с ошибкой
  sigma_direct (доля диапазона) и округляет до шага round_step (люди называют
  «круглые» числа);
* в диалоге сравнивает два варианта по V с ошибкой sigma_compare (в единицах
  полезности): чем ближе варианты, тем чаще он ошибается.

Без ошибок ответы точные, и по ним можно проверить, что метод восстанавливает
функции полезности и веса.
"""

from __future__ import annotations

import math
import random

from .elicitation import EQUAL, PREFER_REF, PREFER_X, Record, direct, run_bisection
from .model import Criterion, MautError
from .project import Project
from .weights import PairAnswer


def exp_shape(a: float):
    """Однокритериальная полезность u(t) = (1 − e^(−a·t)) / (1 − e^(−a)).

    a > 0 — вогнутая (несклонность к риску), a < 0 — выпуклая, a = 0 — линейная.
    """
    if abs(a) < 1e-9:
        return lambda t: t
    d = 1 - math.exp(-a)
    return lambda t: (1 - math.exp(-a * t)) / d


def piecewise_shape(ts: list[float], us: list[float]):
    """Кусочно-линейная u(t) по точкам (для примера из методички)."""
    def u(t):
        t = min(max(t, 0.0), 1.0)
        for (t0, u0), (t1, u1) in zip(zip(ts, us), zip(ts[1:], us[1:])):
            if t <= t1:
                return u0 + (u1 - u0) * (t - t0) / (t1 - t0)
        return us[-1]
    return u


def _solve_t(f, target: float, iters: int = 80) -> float:
    """t ∈ [0, 1], при котором возрастающая f(t) = target."""
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


class SimulatedDM:
    def __init__(self, project: Project, V, sigma_direct: float = 0.0, sigma_compare: float = 0.0,
                 round_step: float = 0.0, seed: int | None = None):
        self.p = project
        self.V = V
        self.sigma_direct = sigma_direct
        self.sigma_compare = sigma_compare
        self.round_step = round_step
        self.rng = random.Random(seed)

    # ---------------------------------------------------------------- построение V

    @staticmethod
    def additive(names: list[str], shapes: dict, weights: dict):
        """V = Σ wi·ui(ti); shapes — словарь «критерий → u(t)»."""
        s = sum(weights.values())
        w = {n: weights[n] / s for n in names}
        return lambda t: sum(w[n] * shapes[n](t[n]) for n in names)

    @staticmethod
    def utility_dependent(names: list[str], a: dict, weights: dict, target: str, delta: float):
        """Нарушение независимости по полезности для критерия target.

        Форма его кривой зависит от уровня прочих критериев: при наилучших
        значениях прочих параметр a, при наихудших a + delta.
        """
        s = sum(weights.values())
        w = {n: weights[n] / s for n in names}

        def V(t):
            others = [t[n] for n in names if n != target]
            level = sum(others) / len(others) if others else 1.0
            total = 0.0
            for n in names:
                aa = a[n] + (delta * (1 - level) if n == target else 0.0)
                total += w[n] * exp_shape(aa)(t[n])
            return total
        return V

    @staticmethod
    def preference_dependent(names: list[str], a: dict, weights: dict, pair: tuple[str, str],
                             third: str, gamma: float):
        """Нарушение независимости по предпочтению (пример с дачей из методички).

        V = Σ wi·ui + γ·u3·(u1 − u2): чем лучше третий критерий, тем важнее
        первый критерий пары относительно второго. Монотонность сохраняется
        при γ ≤ min(w2, w3).
        """
        s = sum(weights.values())
        w = {n: weights[n] / s for n in names}
        if gamma > min(w[pair[1]], w[third]) + 1e-12:
            raise MautError("Слишком большое γ: V перестаёт быть монотонной")
        sh = {n: exp_shape(a[n]) for n in names}
        c1, c2 = pair

        def V(t):
            u = {n: sh[n](t[n]) for n in names}
            return sum(w[n] * u[n] for n in names) + gamma * u[third] * (u[c1] - u[c2])
        return V

    # ---------------------------------------------------------------- вспомогательное

    def _vec(self, fixed: dict[str, float], context: str) -> dict[str, float]:
        """Доли t: заданные критерии + прочие на наилучшем или наихудшем уровне."""
        base = 1.0 if context == "best" else 0.0
        t = {n: base for n in self.p.names()}
        t.update(fixed)
        return t

    def _t(self, name: str, x: float) -> float:
        return self.p.criterion(name).t(x)

    def _noisy_compare(self, diff: float) -> str:
        if self.sigma_compare > 0:
            diff += self.rng.gauss(0, self.sigma_compare)
        if diff > 0:
            return PREFER_X
        if diff < 0:
            return PREFER_REF
        return EQUAL

    def _noisy_value(self, c: Criterion | None, true: float, lo: float, hi: float) -> float:
        span = c.span if c else 1.0
        x = true
        if self.sigma_direct > 0:
            x += self.rng.gauss(0, self.sigma_direct * span)
        if self.round_step > 0:
            step = self.round_step * span
            x = round(x / step) * step
        a, b = min(lo, hi), max(lo, hi)
        margin = 0.01 * (b - a)
        return min(max(x, a + margin), b - margin)

    # ---------------------------------------------------------------- лотереи

    def true_ce(self, name: str, x_lo: float, x_hi: float, context: str) -> float:
        V = self.V
        ev = 0.5 * V(self._vec({name: self._t(name, x_lo)}, context)) + \
            0.5 * V(self._vec({name: self._t(name, x_hi)}, context))
        t = _solve_t(lambda tt: V(self._vec({name: tt}, context)), ev)
        return self.p.criterion(name).x(t)

    def ce_record(self, name: str, x_lo: float, x_hi: float, context: str, mode: str) -> Record:
        c = self.p.criterion(name)
        if mode == "direct":
            return direct(self._noisy_value(c, self.true_ce(name, x_lo, x_hi, context), x_lo, x_hi))
        ev = 0.5 * self.V(self._vec({name: self._t(name, x_lo)}, context)) + \
            0.5 * self.V(self._vec({name: self._t(name, x_hi)}, context))
        worse, better = (x_lo, x_hi) if c.t(x_lo) < c.t(x_hi) else (x_hi, x_lo)

        def oracle(x):
            return self._noisy_compare(self.V(self._vec({name: self._t(name, x)}, context)) - ev)

        return run_bisection(worse, better, self.p.bisection_tol * c.span, oracle)

    # ---------------------------------------------------------------- пары критериев

    def pair_answer(self, a: str, b: str, context: str, mode: str) -> PairAnswer:
        V = self.V
        A = V(self._vec({a: 1.0, b: 0.0}, context))
        B = V(self._vec({a: 0.0, b: 1.0}, context))
        corner = {PREFER_X: "a", PREFER_REF: "b", EQUAL: "equal"}[self._noisy_compare(A - B)]
        if corner == "equal":
            return PairAnswer(a, b, context, "equal")
        if corner == "a":
            scale, other, target = a, b, B   # (x, b худшее) ~ (a худшее, b лучшее)
        else:
            scale, other, target = b, a, A   # (a худшее, y) ~ (a лучшее, b худшее)
        c = self.p.criterion(scale)

        def v_of(tt):
            return V(self._vec({scale: tt, other: 0.0}, context))

        if mode == "direct":
            t_true = _solve_t(v_of, target)
            rec = direct(self._noisy_value(c, c.x(t_true), c.worst, c.best))
        else:
            rec = run_bisection(c.worst, c.best, self.p.bisection_tol * c.span,
                                lambda x: self._noisy_compare(v_of(c.t(x)) - target))
        return PairAnswer(a, b, context, corner, rec)

    def choose_ref(self) -> str:
        """Самый важный критерий: чей переход от худшего к лучшему ценнее всего."""
        return max(self.p.names(), key=lambda n: self.V(self._vec({n: 1.0}, "worst")))

    def p_record(self, mode: str) -> Record:
        ref = self.p.ref
        p_true = self.V(self._vec({ref: 1.0}, "worst"))
        if mode == "direct":
            return direct(self._noisy_value(None, p_true, 0.0, 1.0))
        # вариант с p — лотерея: p·V(все лучшие) + (1 − p)·V(все худшие) = p
        return run_bisection(0.0, 1.0, self.p.bisection_tol,
                             lambda p: self._noisy_compare(p - p_true))

    # ---------------------------------------------------------------- весь опрос

    def fill(self, mode: str = "bisection", checks: bool = True, multiplicative: bool = False) -> None:
        """Пройти все шаги метода, отвечая на вопросы."""
        p = self.p
        for name in p.names():
            for row in p.lotteries(name):
                row = p.lotteries(name)[row["index"]]
                p.set_ce(name, row["u"], self.ce_record(name, row["x_lo"], row["x_hi"], "best", mode))
        if checks:
            for name in p.names():
                for r in p.ui_rows(name):
                    p.set_ui(name, r["u"], self.ce_record(name, r["x_lo"], r["x_hi"], "worst", mode))
        p.set_ref(self.choose_ref())
        if checks:
            for a, b in p.pi_pairs():
                for ctx in ("best", "worst"):
                    p.set_pi(self.pair_answer(a, b, ctx, mode))
        for n in p.names():
            if n != p.ref:
                p.set_weight_answer(self.pair_answer(p.ref, n, "worst", mode))
        if multiplicative:
            p.set_p(self.p_record(mode))
