"""Сквозная проверка окна: модельный ЛПР отвечает через те же кнопки, что и человек.

Нужен X-сервер (на Linux без экрана: xvfb-run -a python -m pytest).
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

tk = pytest.importorskip("tkinter")
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("нет X-сервера", allow_module_level=True)

import app as app_module  # noqa: E402
from maut.simulator import SimulatedDM, exp_shape  # noqa: E402
from tkinter import ttk  # noqa: E402


@pytest.fixture
def gui(monkeypatch):
    # окна-подтверждения в тесте отвечают «да», сообщения не показываются
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda *a, **k: None)
    errors = []
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda title, msg: errors.append(msg))
    root = tk.Tk()
    a = app_module.App(root)
    a.errors = errors
    yield a
    a.dirty = False
    root.destroy()


def find(widget, cls, text=None):
    for w in widget.winfo_children():
        if isinstance(w, cls) and (text is None or w.cget("text") == text):
            return w
        r = find(w, cls, text)
        if r is not None:
            return r
    return None


def answer_panel(panel, mode, true_value, compare):
    """Пройти опрос на панели: прямой ввод — ввести true_value, диалог — отвечать compare(x)."""
    panel.mode.set(mode)
    panel._begin()
    for _ in range(100):
        if not panel.active:
            return
        entry = find(panel.body, ttk.Entry)
        if entry is not None:
            entry.delete(0, "end")
            entry.insert(0, f"{true_value:.4f}".replace(".", ","))
            find(panel.body, ttk.Button, "Принять").invoke()
        else:
            panel._answer(compare(panel.session.current()))
    raise AssertionError("опрос не закончился")


def test_full_run_through_window(gui):
    a = gui
    root = a.root
    # 1. критерии через форму
    tab = a.tabs[0]
    for name, unit, worst, best in (("Цена", "тыс", "100", "50"), ("Качество", "балл", "1", "10"),
                                    ("Срок", "дн", "30", "5")):
        tab.vars["name"].set(name)
        tab.vars["unit"].set(unit)
        tab.vars["worst"].set(worst)
        tab.vars["best"].set(best)
        tab._add()
    assert a.project.names() == ["Цена", "Качество", "Срок"]
    tab.points.set("5")
    tab._apply()

    p = a.project
    names = p.names()
    w_true = {"Цена": 0.5, "Качество": 0.3, "Срок": 0.2}
    dm = SimulatedDM(p, SimulatedDM.additive(names, {n: exp_shape(1.5) for n in names}, w_true))

    # 2. лотереи: первый критерий диалогом, второй прямым вводом, третий обоими
    a.nb.select(1)
    root.update()
    ct = a.tabs[1]
    for name, mode in zip(names, ("bisection", "direct", "both")):
        ct.crit.selection_set(name)
        root.update()
        for _ in range(3):
            iid = ct.lots.selection()[0]
            row = p.lotteries(name)[int(iid)]
            c = p.criterion(name)
            ev = 0.5 * dm.V(dm._vec({name: c.t(row["x_lo"])}, "best")) + \
                0.5 * dm.V(dm._vec({name: c.t(row["x_hi"])}, "best"))
            true = dm.true_ce(name, row["x_lo"], row["x_hi"], "best")
            answer_panel(ct.panel, mode, true,
                         lambda x: dm._noisy_compare(dm.V(dm._vec({name: c.t(x)}, "best")) - ev))
            root.update()
        assert p.curve_complete(name), name
    assert len(p.mode_comparisons()) == 3

    # 3. независимость по полезности
    a.nb.select(2)
    root.update()
    it = a.tabs[2]
    for name in names:
        it.ui_tree.selection_set(f"{name}|0.5")
        root.update()
        row = p.ui_rows(name)[0]
        true = dm.true_ce(name, row["x_lo"], row["x_hi"], "worst")
        answer_panel(it.ui_panel, "direct", true, None)
    assert all(p.ui_status(n) for n in names)

    # опорный критерий и независимость по предпочтению
    it.ref.set("Цена")
    it._set_ref()
    for a_, b_ in p.pi_pairs():
        for ctx in ("best", "worst"):
            it.pi_tree.selection_set(f"{a_}|{b_}")
            it.ctx.set(ctx)
            it._pi_select()
            ans = dm.pair_answer(a_, b_, ctx, "direct")
            it.pair._corner(ans.corner)
            answer_panel(it.pair.q, "direct", ans.record.value, None)
    assert p.pi_status() is True

    # 4. веса диалогом и p
    a.nb.select(3)
    root.update()
    wt = a.tabs[3]
    for n in names[1:]:
        wt.tree.selection_set(n)
        wt._select()
        ans = dm.pair_answer("Цена", n, "worst", "direct")
        wt.pair._corner(ans.corner)
        sc = p.criterion(ans.scale)
        other = n if ans.corner == "a" else "Цена"
        target = dm.V(dm._vec({"Цена": 0.0, n: 1.0} if ans.corner == "a" else {"Цена": 1.0, n: 0.0}, "worst"))
        answer_panel(wt.pair.q, "bisection", None,
                     lambda x: dm._noisy_compare(dm.V(dm._vec({sc.name: sc.t(x), other: 0.0}, "worst")) - target))
    w = p.weights()
    for n in names:
        assert w[n] == pytest.approx(w_true[n], abs=0.03)
    wt.model.set("multiplicative")
    wt._set_model()
    answer_panel(wt.p_panel, "both", 0.5, lambda x: dm._noisy_compare(x - 0.5))
    assert p.p_ref and abs(p.p_ref[-1].value - 0.5) < 0.02

    # 5. альтернативы через форму
    a.nb.select(4)
    root.update()
    at = a.tabs[4]
    for nm, vals in (("X", ("60", "8", "10")), ("Y", ("90", "9", "6"))):
        at.vars["name"].set(nm)
        for n, val in zip(names, vals):
            at.vars[n].set(val)
        at._add()
    res = p.evaluate()
    assert len(res["rows"]) == 2
    assert len(at.res.get_children()) == 2

    # 6. сравнение режимов и сохранение
    a.nb.select(5)
    root.update()
    root.update()
    assert len(a.tabs[5].tree.get_children()) == 4   # 3 лотереи + p
    assert not a.errors, a.errors
