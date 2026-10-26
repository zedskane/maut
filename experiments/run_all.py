"""Пересчитать все опыты: таблицы (CSV) и графики (PNG) в experiments/results.

python experiments/run_all.py      (около минуты)
"""

import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent

for name in ("exp_modes", "exp_points", "exp_independence", "exp_airport"):
    print(f"=== {name}")
    runpy.run_path(str(HERE / f"{name}.py"), run_name="__main__")
