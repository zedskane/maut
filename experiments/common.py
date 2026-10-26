"""Общее для экспериментов: модельные ЛПР, метрики, оформление графиков."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from maut import Criterion, Project  # noqa: E402
from maut.simulator import SimulatedDM, exp_shape  # noqa: E402

RESULTS = ROOT / "experiments" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

# категориальная палитра (проверена на различимость при дальтонизме), порядок фиксирован
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"

GRID_T = np.linspace(0, 1, 101)


def style(ax, title=None, xlabel=None, ylabel=None):
    """Тонкая сетка, приглушённые оси, текст нейтральным цветом."""
    if title:
        ax.set_title(title, color=INK, fontsize=11)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK2)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK2)
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#b5b4ae")
    ax.tick_params(colors=INK2)


def one_criterion(levels: int = 2, tol: float = 0.01) -> Project:
    """Проект с одним критерием 0…100 (лучше больше) — для опытов с одной кривой."""
    p = Project("опыт", [Criterion("x", "", 0, 100)], levels=levels)
    p.bisection_tol = tol
    return p


def curve_error(p: Project, name: str, true_u) -> tuple[float, float]:
    """Средняя и максимальная |U_оценка − U_истинная| по сетке из 101 точки."""
    u = p.utility(name)
    c = p.criterion(name)
    est = np.array([u(c.x(t)) for t in GRID_T])
    tru = np.array([true_u(t) for t in GRID_T])
    d = np.abs(est - tru)
    return float(d.mean()), float(d.max())


def fill_curve(p: Project, dm: SimulatedDM, name: str, mode: str) -> int:
    """Провести все лотереи одного критерия, вернуть число вопросов."""
    q = 0
    for i in range(len(p.plan())):
        row = p.lotteries(name)[i]
        rec = dm.ce_record(name, row["x_lo"], row["x_hi"], "best", mode)
        p.set_ce(name, row["u"], rec)
        q += rec.questions
    return q


def kendall_tau(a, b) -> float:
    n = len(a)
    s = 0
    for i in range(n):
        for j in range(i + 1, n):
            s += np.sign(a[i] - a[j]) * np.sign(b[i] - b[j])
    return 2 * s / (n * (n - 1))


def three_criteria(levels: int = 2, tol: float = 0.01) -> Project:
    p = Project("опыт", [Criterion("C1", "", 0, 100), Criterion("C2", "", 0, 100),
                         Criterion("C3", "", 0, 100)], levels=levels)
    p.bisection_tol = tol
    return p


def random_additive_dm(p: Project, rng: np.random.Generator, **noise) -> tuple[SimulatedDM, dict, dict]:
    names = p.names()
    a = {n: float(rng.uniform(-3, 3)) for n in names}
    w = dict(zip(names, rng.dirichlet([2.0] * len(names))))
    shapes = {n: exp_shape(a[n]) for n in names}
    V = SimulatedDM.additive(names, shapes, w)
    dm = SimulatedDM(p, V, seed=int(rng.integers(1 << 30)), **noise)
    return dm, shapes, w


def save_csv(name: str, header: list[str], rows: list[list]) -> Path:
    path = RESULTS / name
    with open(path, "w", encoding="utf-8") as f:
        f.write(";".join(header) + "\n")
        for r in rows:
            f.write(";".join(f"{x:.4f}" if isinstance(x, float) else str(x) for x in r) + "\n")
    return path
