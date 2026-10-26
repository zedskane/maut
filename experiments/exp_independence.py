"""Опыт 3. Как часто проверки независимости ошибаются и какой допуск выбрать.

Независимость по полезности: ЛПР с нарушением силы δ (форма кривой C1 при
наихудших прочих — a + δ, при наилучших — a). δ = 0 — условие выполнено, доля
срабатываний = ложные тревоги.
Независимость по предпочтению: V = Σ wi·ui + γ·u3·(u1 − u2), γ = 0 — условие
выполнено.
Проверка приближённая, как в методичке: одна лотерея / одна пара.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from common import INK2, PALETTE, RESULTS, save_csv, style, three_criteria
from maut.simulator import SimulatedDM

N = 600
TOLS = (0.02, 0.05, 0.10)
MODES = [("диалог, шум 0,02", "bisection", {"sigma_compare": 0.02}),
         ("прямой ввод, ошибка 3 %", "direct", {"sigma_direct": 0.03}),
         ("прямой ввод, ошибка 5 %", "direct", {"sigma_direct": 0.05})]


def ui_trial(rng, delta, mode, kw):
    p = three_criteria()
    names = p.names()
    a = {n: float(rng.uniform(-1, 1)) for n in names}
    w = {"C1": 0.4, "C2": 0.3, "C3": 0.3}
    V = SimulatedDM.utility_dependent(names, a, w, "C1", delta)
    dm = SimulatedDM(p, V, seed=int(rng.integers(1 << 30)), **kw)
    exact = SimulatedDM(p, V)
    b = dm.ce_record("C1", 0, 100, "best", mode).value
    wv = dm.ce_record("C1", 0, 100, "worst", mode).value
    true = abs(exact.true_ce("C1", 0, 100, "best") - exact.true_ce("C1", 0, 100, "worst")) / 100
    return abs(b - wv) / 100, False, true


def pi_trial(rng, gamma, mode, kw):
    p = three_criteria()
    names = p.names()
    a = {n: float(rng.uniform(-1, 1)) for n in names}
    w = {"C1": 0.4, "C2": 0.3, "C3": 0.3}
    V = SimulatedDM.preference_dependent(names, a, w, ("C1", "C2"), "C3", gamma)
    dm = SimulatedDM(p, V, seed=int(rng.integers(1 << 30)), **kw)
    exact = SimulatedDM(p, V)
    ab, aw = dm.pair_answer("C1", "C2", "best", mode), dm.pair_answer("C1", "C2", "worst", mode)
    eb, ew = exact.pair_answer("C1", "C2", "best", "bisection"), exact.pair_answer("C1", "C2", "worst", "bisection")
    flip = ab.corner != aw.corner
    diff = 1.0 if flip else abs(ab.record.value - aw.record.value) / 100
    true = 1.0 if eb.corner != ew.corner else abs(eb.record.value - ew.record.value) / 100
    return diff, flip, true


def run():
    rows = []
    for check, trial, strengths in (("по полезности", ui_trial, (0.0, 0.5, 1.0, 2.0, 4.0)),
                                    ("по предпочтению", pi_trial, (0.0, 0.05, 0.1, 0.2, 0.3))):
        for label, mode, kw in MODES:
            for s in strengths:
                rng = np.random.default_rng(11)
                diffs, trues = [], []
                for _ in range(N):
                    d, _flip, t = trial(rng, s, mode, kw)
                    diffs.append(d)
                    trues.append(t)
                diffs = np.array(diffs)
                rows.append([check, label, s, float(np.mean(trues))] +
                            [float(np.mean(diffs > tol + 1e-12)) for tol in TOLS])
    save_csv("independence.csv", ["проверка", "режим", "сила_нарушения", "истинная_разница"] +
             [f"срабатываний_допуск_{int(t * 100)}%" for t in TOLS], rows)
    return rows


def plot(rows):
    fig = Figure(figsize=(9.6, 3.8), dpi=150, layout="constrained")
    for k, (check, xlabel) in enumerate((("по полезности", "Сила нарушения δ"),
                                         ("по предпочтению", "Сила нарушения γ"))):
        ax = fig.add_subplot(1, 2, k + 1)
        for i, (label, *_r) in enumerate(MODES):
            rr = [r for r in rows if r[0] == check and r[1] == label]
            ax.plot([r[2] for r in rr], [r[6] for r in rr], "-o", color=PALETTE[i], lw=2, ms=7, label=label)
        style(ax, f"Независимость {check}: допуск 10 %", xlabel, "Доля случаев «нарушено»")
        ax.set_ylim(-0.02, 1.02)
        ax.text(0.97, 0.45, "значение при 0 —\nдоля ложных тревог", transform=ax.transAxes, fontsize=8, color=INK2, ha="right")
        if k == 1:
            ax.legend(frameon=False, loc="lower right", fontsize=8)
    fig.savefig(RESULTS / "independence.png")


if __name__ == "__main__":
    rows = run()
    plot(rows)
    for r in rows:
        print([x if not isinstance(x, float) else round(x, 3) for x in r])
