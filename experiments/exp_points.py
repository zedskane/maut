"""Опыт 2. Сколько точек нужно на кривой полезности: 3, 5, 9 или 17.

Случайная форма u(t) с a ~ U(−3, 3). Три режима ответов: точные (предел метода),
диалог с шумом сравнений 0,02 и точностью 1 %, прямой ввод с ошибкой 5 % диапазона.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from common import INK2, PALETTE, RESULTS, curve_error, fill_curve, one_criterion, save_csv, style
from maut.simulator import SimulatedDM, exp_shape

N = 400
REGIMES = [("точные ответы", "bisection", {}, 0.001),
           ("диалог, шум 0,02", "bisection", {"sigma_compare": 0.02}, 0.01),
           ("прямой ввод, ошибка 5 %", "direct", {"sigma_direct": 0.05}, 0.01)]


def run():
    rows = []
    for label, mode, kw, tol in REGIMES:
        for levels in (1, 2, 3, 4):
            rng = np.random.default_rng(3)
            errs, qs = [], []
            for _ in range(N):
                p = one_criterion(levels, tol)
                u = exp_shape(rng.uniform(-3, 3))
                dm = SimulatedDM(p, lambda t: u(t["x"]), seed=int(rng.integers(1 << 30)), **kw)
                qs.append(fill_curve(p, dm, "x", mode))
                errs.append(curve_error(p, "x", u)[0])
            rows.append([label, 2 ** levels + 1, float(np.mean(qs)), float(np.mean(errs))])
    save_csv("points.csv", ["режим", "точек", "вопросов", "ср_ошибка"], rows)
    return rows


def plot(rows):
    fig = Figure(figsize=(7.2, 4.0), dpi=150, layout="constrained")
    ax = fig.add_subplot(111)
    for i, (label, *_rest) in enumerate(REGIMES):
        rr = [r for r in rows if r[0] == label]
        ax.plot([r[1] for r in rr], [r[3] for r in rr], "-o", color=PALETTE[i], lw=2, ms=8, label=label)
    rr = [r for r in rows if r[0] == REGIMES[1][0]]
    for r in rr:
        ax.annotate(f"{r[2]:.0f} вопр.", (r[1], r[3]), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=8, color=INK2)
    style(ax, "Ошибка кривой полезности в зависимости от числа точек",
          "Точек на кривой", "Средняя |U оценка − U истинная|")
    ax.set_xticks([3, 5, 9, 17])
    ax.set_ylim(0, None)
    ax.legend(frameon=False)
    fig.savefig(RESULTS / "points.png")


if __name__ == "__main__":
    rows = run()
    plot(rows)
    for r in rows:
        print(r)
