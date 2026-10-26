"""Опыт 1. Прямой ввод против диалога «выше/ниже».

A. Одна кривая (5 точек, 3 лотереи), случайная форма u(t) = (1 − e^(−a·t))/(1 − e^(−a)),
   a ~ U(−3, 3). Прямой ввод: ЛПР называет эквивалент с ошибкой σ_d (доля диапазона).
   Диалог: ЛПР сравнивает варианты по полезности с ошибкой σ_b, точность 1 %.
B. Диалог при разной точности остановки (σ_b = 0,02): вопросы против ошибки.
C. Весь метод (3 критерия, веса) и ранжирование 30 случайных альтернатив:
   совпадение порядка с истинным (τ Кендалла) и доля верно найденной лучшей.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from common import (INK2, PALETTE, curve_error, fill_curve, kendall_tau, one_criterion,
                    random_additive_dm, save_csv, style, three_criteria, RESULTS)
from maut import Alternative
from maut.simulator import SimulatedDM, exp_shape

N_A = 500
N_C = 200


def run_curve(mode, sigma, tol=0.01, n=N_A, seed=1):
    rng = np.random.default_rng(seed)
    errs, maxs, qs = [], [], []
    for _ in range(n):
        p = one_criterion(2, tol)
        a = rng.uniform(-3, 3)
        u = exp_shape(a)
        kw = {"sigma_direct": sigma} if mode == "direct" else {"sigma_compare": sigma}
        dm = SimulatedDM(p, lambda t: u(t["x"]), seed=int(rng.integers(1 << 30)), **kw)
        qs.append(fill_curve(p, dm, "x", mode))
        m, mx = curve_error(p, "x", u)
        errs.append(m)
        maxs.append(mx)
    return float(np.mean(qs)), float(np.mean(errs)), float(np.mean(maxs)), float(np.percentile(maxs, 95))


def part_a():
    rows = []
    for s in (0.0, 0.03, 0.05, 0.10):
        rows.append(["прямой ввод", s, *run_curve("direct", s)])
    for s in (0.0, 0.01, 0.02, 0.05):
        rows.append(["диалог", s, *run_curve("bisection", s)])
    save_csv("modes_curve.csv", ["режим", "шум", "вопросов", "ср_ошибка", "ср_макс_ошибка", "макс_95%"], rows)
    return rows


def part_b():
    rows = []
    for tol in (0.005, 0.01, 0.02, 0.05, 0.10):
        rows.append([tol, *run_curve("bisection", 0.02, tol)])
    save_csv("modes_tol.csv", ["точность", "вопросов", "ср_ошибка", "ср_макс_ошибка", "макс_95%"], rows)
    return rows


def part_c():
    configs = [("диалог", 0.0), ("прямой ввод", 0.05), ("прямой ввод", 0.10),
               ("диалог", 0.02), ("диалог", 0.05)]
    rows = []
    for mode_name, s in configs:
        mode = "direct" if mode_name == "прямой ввод" else "bisection"
        rng = np.random.default_rng(7)
        taus, hits, qs, werr = [], [], [], []
        for _ in range(N_C):
            p = three_criteria()
            kw = {"sigma_direct": s} if mode == "direct" else {"sigma_compare": s}
            dm, shapes, w = random_additive_dm(p, rng, **kw)
            dm.fill(mode, checks=False)
            qs.append(sum(r.questions for d in p.curves.values() for recs in d.values() for r in recs[-1:]) +
                      sum(a.record.questions + 1 if a.record else 1 for a in p.weight_answers.values()))
            alts = [Alternative(str(i), {n: float(rng.uniform(0, 100)) for n in p.names()}) for i in range(30)]
            est = [r["U"] for r in p.evaluate(alts)["rows"]]
            tru = [dm.V({n: a.values[n] / 100 for n in p.names()}) for a in alts]
            taus.append(kendall_tau(est, tru))
            hits.append(int(np.argmax(est) == np.argmax(tru)))
            west = p.weights()
            werr.append(max(abs(west[n] - w[n]) for n in p.names()))
        rows.append([mode_name, s, float(np.mean(qs)), float(np.mean(werr)), float(np.mean(taus)),
                     float(np.mean(hits))])
    save_csv("modes_ranking.csv", ["режим", "шум", "вопросов_всего", "ошибка_весов", "тау_Кендалла",
                                   "лучшая_верно"], rows)
    return rows


def plot(a_rows, b_rows):
    fig = Figure(figsize=(7.2, 4.2), dpi=150, layout="constrained")
    ax = fig.add_subplot(111)
    xs = [r[1] for r in b_rows]
    ys = [r[2] for r in b_rows]
    ax.plot(xs, ys, "-o", color=PALETTE[0], lw=2, ms=8, label="Диалог (шум сравнений 0,02)")
    for r in b_rows:
        ax.annotate(f"{r[0] * 100:g} %", (r[1], r[2]), textcoords="offset points", xytext=(0, -16),
                    fontsize=8, color=INK2, ha="center")
    ax.annotate("точность остановки диалога", (b_rows[2][1], b_rows[2][2]), textcoords="offset points",
                xytext=(0, 14), fontsize=8, color=INK2, ha="center")
    floor = a_rows[0][3]
    ax.axhline(floor, color=INK2, lw=1, ls="--")
    ax.text(5, floor - 0.0006, "предел при точных ответах (ошибка интерполяции по 5 точкам)", fontsize=8,
            color=INK2, va="top", ha="left")
    direct = [r for r in a_rows if r[0] == "прямой ввод" and r[1] > 0]
    ax.plot([r[2] for r in direct], [r[3] for r in direct], "s", color=PALETTE[1], ms=9,
            label="Прямой ввод (3 ответа)", linestyle="none")
    for r in direct:
        ax.annotate(f"ошибка ввода {r[1] * 100:g} %", (r[2], r[3]), textcoords="offset points",
                    xytext=(8, -3), fontsize=8, color=INK2)
    style(ax, "Точность кривой полезности и число вопросов (5 точек)",
          "Вопросов на одну кривую", "Средняя |U оценка − U истинная|")
    ax.set_xlim(0, 27)
    ax.set_ylim(0, None)
    ax.legend(frameon=False, loc="upper right")
    fig.savefig(RESULTS / "modes.png")


if __name__ == "__main__":
    a = part_a()
    b = part_b()
    c = part_c()
    plot(a, b)
    for name, rows in (("A", a), ("B", b), ("C", c)):
        print(name)
        for r in rows:
            print("  ", r)
