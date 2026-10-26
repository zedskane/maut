"""Реализация метода MAUT (многокритериальная теория полезности).

Пакет не зависит от интерфейса: окно (app.py), консольный запуск (run.py),
тесты и эксперименты работают с одним и тем же кодом.
"""

from .model import Criterion, Alternative, MautError
from .elicitation import BisectionSession, Record
from .utility import UtilityFunction, lottery_plan, levels_for_points, points_for_levels
from .weights import PairAnswer, solve_k
from .project import Project

__all__ = [
    "Criterion", "Alternative", "MautError",
    "BisectionSession", "Record",
    "UtilityFunction", "lottery_plan", "levels_for_points", "points_for_levels",
    "PairAnswer", "solve_k",
    "Project",
]
