"""Опыт 4. Пример «Аэропорт»: чувствительность результата и сравнение моделей.

A. Вес стоимости w1 от 0,2 до 0,8, веса времени и шума в прежнем отношении 2 : 3.
B. Случайные отклонения весов (±10, 20, 30 %) и точек кривых (ошибка 3 % диапазона):
   как часто лучшей остаётся та же площадка.
C. Мультипликативная модель при разных p (p = 0,5 даёт Σki = 1, то есть аддитивную).
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from common import INK2, PALETTE, RESULTS, ROOT, save_csv, style
from maut import Project, UtilityFunction
from maut.elicitation import direct
from maut.weights import multiplicative, solve_k

P = Project.load(ROOT / "examples" / "airport.json")
NAMES = P.names()
ALTS = P.alternatives
UTILS = P.utilities()
W = P.weights()
U_ALT = {a.name: {n: UTILS[n](a.values[n]) for n in NAMES} for a in ALTS}


def total(w, u=U_ALT):
    return {a: sum(w[n] * u[a][n] for n in NAMES) for a in u}


def part_a():
    rows = []
    rest = W[NAMES[1]] + W[NAMES[2]]
    for w1 in np.round(np.arange(0.2, 0.801, 0.02), 2):
        w = {NAMES[0]: w1, NAMES[1]: (1 - w1) * W[NAMES[1]] / rest, NAMES[2]: (1 - w1) * W[NAMES[2]] / rest}
        t = total(w)
        rows.append([float(w1)] + [t[a.name] for a in ALTS])
    save_csv("airport_weight_sweep.csv", ["w_стоимость"] + [a.name for a in ALTS], rows)
    # где меняется лидер
    switches = []
    for r0, r1 in zip(rows, rows[1:]):
        l0 = ALTS[int(np.argmax(r0[1:]))].name
        l1 = ALTS[int(np.argmax(r1[1:]))].name
        if l0 != l1:
            switches.append((r0[0], r1[0], l0, l1))
    return rows, switches


def perturbed_utils(rng, sigma):
    out = {}
    for n in NAMES:
        c = P.criterion(n)
        pts = sorted(P.known_points(n).items())
        xs = [x for _, x in pts]
        ts = [c.t(x) for x in xs]
        new_t = [ts[0]] + sorted(float(np.clip(t + rng.normal(0, sigma), 0.01, 0.99)) for t in ts[1:-1]) + [ts[-1]]
        if any(b <= a for a, b in zip(new_t, new_t[1:])):
            new_t = ts
        out[n] = UtilityFunction(c, [(c.x(t), u) for t, (u, _) in zip(new_t, pts)])
    return {a.name: {n: out[n](a.values[n]) for n in NAMES} for a in ALTS}


def part_b(n=4000):
    rows = []
    for eps in (0.1, 0.2, 0.3):
        for sigma in (0.0, 0.03):
            rng = np.random.default_rng(5)
            wins = {a.name: 0 for a in ALTS}
            for _ in range(n):
                w = {k: v * rng.uniform(1 - eps, 1 + eps) for k, v in W.items()}
                s = sum(w.values())
                w = {k: v / s for k, v in w.items()}
                u = perturbed_utils(rng, sigma) if sigma else U_ALT
                t = total(w, u)
                wins[max(t, key=t.get)] += 1
            rows.append([eps, sigma] + [wins[a.name] / n for a in ALTS])
    save_csv("airport_montecarlo.csv", ["отклонение_весов", "ошибка_точек"] + [a.name for a in ALTS], rows)
    return rows


def part_c():
    rows = []
    for pv in (0.3, 0.4, 0.5, 0.55, 0.6, 0.7):
        q = Project.from_dict(P.to_dict())
        q.p_ref = [direct(pv)]
        try:
            ks = q.scaling()
        except Exception as e:  # ki ≥ 1 при больших p
            rows.append([pv, float("nan"), float("nan")] + [float("nan")] * len(ALTS) + [str(e)[:40]])
            continue
        k = solve_k(list(ks.values()))
        us = {a.name: multiplicative([ks[n] for n in NAMES], k, [U_ALT[a.name][n] for n in NAMES]) for a in ALTS}
        order = " > ".join(sorted(us, key=lambda a: -us[a]))
        rows.append([pv, sum(ks.values()), k] + [us[a.name] for a in ALTS] + [order])
    save_csv("airport_multiplicative.csv", ["p", "сумма_ki", "k"] + [a.name for a in ALTS] + ["порядок"], rows)
    return rows


def plot_a(rows, switches):
    fig = Figure(figsize=(7.2, 4.2), dpi=150, layout="constrained")
    ax = fig.add_subplot(111)
    xs = [r[0] for r in rows]
    ends = []
    for i, a in enumerate(ALTS):
        ys = [r[i + 1] for r in rows]
        ax.plot(xs, ys, color=PALETTE[i], lw=2, label=a.name)
        ends.append([ys[-1], a.name])
    # подписи на правом краю раздвигаются, чтобы не наезжали друг на друга
    ends.sort()
    for j in range(1, len(ends)):
        ends[j][0] = max(ends[j][0], ends[j - 1][0] + 0.025)
    for y, name in ends:
        ax.text(xs[-1] + 0.01, y, name, color=INK2, fontsize=8, va="center")
    ax.axvline(W[NAMES[0]], color=INK2, lw=1, ls="--")
    ax.text(W[NAMES[0]] + 0.005, 0.985, "веса ЛПР\n(w1 = 0,5)", fontsize=8, color=INK2, va="top",
            transform=ax.get_xaxis_transform())
    for lo, hi, _l0, l1 in switches:
        ax.axvspan(lo, hi, color="#d9d8d3", alpha=0.6, lw=0)
    lo, hi, _l0, l1 = switches[-1]
    ax.text(hi + 0.005, 0.02, f"смена лучшей:\nдальше «{l1}»", fontsize=8, color=INK2,
            transform=ax.get_xaxis_transform())
    style(ax, "Чувствительность к весу стоимости", "Вес стоимости w1 (w2 : w3 = 2 : 3)",
          "Многокритериальная полезность U")
    ax.set_xlim(0.2, 0.92)
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0.0, 0.0))
    fig.savefig(RESULTS / "airport_sweep.png")


if __name__ == "__main__":
    a, sw = part_a()
    plot_a(a, sw)
    print("смена лидера:", sw)
    for r in part_b():
        print([round(x, 3) if isinstance(x, float) else x for x in r])
    for r in part_c():
        print([round(x, 3) if isinstance(x, float) else x for x in r])
