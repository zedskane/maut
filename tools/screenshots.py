"""Снимки окна для отчёта (запускать под X-сервером, например xvfb-run).

python tools/screenshots.py docs/img
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

import app as app_module  # noqa: E402
from maut.elicitation import PREFER_REF, PREFER_X  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/img")
out.mkdir(parents=True, exist_ok=True)

root = tk.Tk()
a = app_module.App(root)
root.geometry("1360x860+0+0")


def shot(name):
    for _ in range(5):
        root.update()
    root.after(300)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out / f"{name}.png")
    print("saved", name)


def tab(i):
    a.nb.select(i)
    root.update()
    a.tabs[i].refresh()
    root.update()


# --- заполненный пример: все вкладки
a.load_example("airport.json")
for i, name in enumerate(["criteria", "curves", "independence", "weights", "alternatives", "compare"]):
    tab(i)
    if name == "curves":
        t = a.tabs[1]
        t.crit.selection_set("Стоимость")
        root.update()
    if name == "independence":
        t = a.tabs[2]
    shot(name)

# вкладка независимости по предпочтению
t = a.tabs[2]
tab(2)
t.inner.select(1)
root.update()
shot("independence_pi")

# мультипликативная модель
a.project.model = "multiplicative"
a.changed()
tab(3)
shot("weights_mult")
tab(4)
shot("alternatives_mult")
a.project.model = "additive"

# --- диалог в процессе: пустой пример, первая лотерея по стоимости
a.dirty = False
a.load_example("airport_empty.json")
tab(1)
t = a.tabs[1]
t.panel.mode.set("bisection")
t.panel._begin()
root.update()
t.panel._answer(PREFER_X)     # гарантированные 150 млн лучше лотереи → CE хуже 150
root.update()
t.panel._answer(PREFER_REF)   # лотерея лучше гарантированных 175 млн → CE между 175 и 150
root.update()
shot("dialog")

# прямой ввод
t.panel._cancel()
t.panel.mode.set("direct")
t.panel._begin()
shot("direct")
t.panel._cancel()

# пара критериев: шаг 2 на вкладке весов
a.load_example("airport.json")
a.project.weight_answers.pop("Время в пути")
a.changed()
tab(3)
w = a.tabs[3]
w.tree.selection_set("Время в пути")
root.update()
w.pair._corner("a")
root.update()
w.pair.q.mode.set("bisection")
w.pair.q._begin()
root.update()
w.pair.q._answer(PREFER_REF)
root.update()
shot("pair_dialog")

a.dirty = False
root.destroy()
