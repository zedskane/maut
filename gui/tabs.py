"""Вкладки окна — по одной на шаг метода."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from maut.model import Alternative, Criterion, MautError, fmt, quantum
from maut.utility import levels_for_points

from .widgets import PairPanel, QuestionPanel, draw_lottery, parse_float, show_error

OK, BAD, NONE = "✓", "✗", "—"


def mark(st) -> str:
    return {True: OK, False: BAD}.get(st, NONE)


def v(c: Criterion, x) -> str:
    if x is None:
        return ""
    return f"{fmt(x, c.span)} {c.unit}".strip()


def pct(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


def make_tree(master, columns: list[tuple[str, str, int]], height: int = 8) -> ttk.Treeview:
    frame = ttk.Frame(master)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height,
                        selectmode="browse")
    for key, title, width in columns:
        tree.heading(key, text=title)
        tree.column(key, width=width, anchor="w", stretch=True)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="left", fill="y")
    tree.frame = frame
    return tree


def selected(tree: ttk.Treeview) -> str | None:
    sel = tree.selection()
    return sel[0] if sel else None


def select(tree: ttk.Treeview, iid: str | None) -> None:
    if iid and tree.exists(iid):
        tree.selection_set(iid)
        tree.see(iid)


def plot_frame(master, size=(4.6, 3.4)):
    fig = Figure(figsize=size, dpi=100, layout="constrained")
    canvas = FigureCanvasTkAgg(fig, master=master)
    return fig, canvas


# ======================================================================= критерии


class CriteriaTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb, padding=8)
        self.app = app
        left = ttk.Frame(self)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Критерии и диапазоны оценок", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        ttk.Label(left, text="Наилучшее значение может быть меньше наихудшего (стоимость, время): "
                             "направление задаётся этими двумя числами.", foreground="#555").pack(anchor="w")
        self.tree = make_tree(left, [("name", "Критерий", 220), ("unit", "Ед. изм.", 90),
                                     ("worst", "Наихудшее", 100), ("best", "Наилучшее", 100),
                                     ("dir", "Лучше, когда", 120)], height=10)
        self.tree.frame.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.LabelFrame(left, text="Критерий", padding=8)
        form.pack(fill="x")
        self.vars = {}
        for i, (key, label, w) in enumerate((("name", "Название", 30), ("unit", "Ед. изм.", 12),
                                             ("worst", "Наихудшее", 12), ("best", "Наилучшее", 12))):
            ttk.Label(form, text=label).grid(row=0, column=2 * i, sticky="w", padx=(0, 4))
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=w).grid(row=0, column=2 * i + 1, padx=(0, 12))
            self.vars[key] = var
        bf = ttk.Frame(form)
        bf.grid(row=1, column=0, columnspan=8, sticky="w", pady=(8, 0))
        ttk.Button(bf, text="Добавить", command=self._add).pack(side="left")
        ttk.Button(bf, text="Изменить выбранный", command=self._update).pack(side="left", padx=6)
        ttk.Button(bf, text="Удалить выбранный", command=self._delete).pack(side="left")

        right = ttk.LabelFrame(self, text="Параметры метода", padding=8)
        right.pack(side="left", fill="y", padx=(10, 0))
        self.points = tk.StringVar()
        self.tol = tk.StringVar()
        self.ui_tol = tk.StringVar()
        self.pi_tol = tk.StringVar()
        self.ui_full = tk.BooleanVar()
        self.pi_full = tk.BooleanVar()
        r = 0
        ttk.Label(right, text="Точек на кривой полезности").grid(row=r, column=0, sticky="w")
        ttk.Combobox(right, textvariable=self.points, values=["3", "5", "9", "17"], width=6,
                     state="readonly").grid(row=r, column=1, sticky="w")
        r += 1
        ttk.Label(right, text="3 точки — 1 лотерея, 5 — 3, 9 — 7, 17 — 15", foreground="#555").grid(
            row=r, column=0, columnspan=2, sticky="w")
        r += 1
        for label, var in (("Точность диалога, % диапазона", self.tol),
                           ("Допуск проверки по полезности, %", self.ui_tol),
                           ("Допуск проверки по предпочтению, %", self.pi_tol)):
            ttk.Label(right, text=label).grid(row=r, column=0, sticky="w", pady=(6, 0))
            ttk.Entry(right, textvariable=var, width=8).grid(row=r, column=1, sticky="w", pady=(6, 0))
            r += 1
        ttk.Checkbutton(right, text="Полная проверка по полезности (все лотереи)",
                        variable=self.ui_full).grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 0))
        r += 1
        ttk.Checkbutton(right, text="Полная проверка по предпочтению (все пары)",
                        variable=self.pi_full).grid(row=r, column=0, columnspan=2, sticky="w")
        r += 1
        ttk.Button(right, text="Применить", command=self._apply).grid(row=r, column=0, sticky="w", pady=10)
        r += 1
        ttk.Label(right, wraplength=330, justify="left", foreground="#555", text=(
            "Без полной проверки независимость по полезности проверяется только на первой лотерее "
            "(худшее/лучшее), а независимость по предпочтению — только для пар с опорным критерием. "
            "Так делается приближённая проверка из методички.")).grid(row=r, column=0, columnspan=2, sticky="w")
        # правая панель должна получить свою ширину первой, таблица сжимается
        left.pack_forget()
        right.pack_forget()
        right.pack(side="right", fill="y", padx=(10, 0))
        left.pack(side="left", fill="both", expand=True)

    def refresh(self):
        p = self.app.project
        keep = selected(self.tree)
        self.tree.delete(*self.tree.get_children())
        for c in p.criteria:
            self.tree.insert("", "end", iid=c.name, values=(
                c.name, c.unit, fmt(c.worst, c.span), fmt(c.best, c.span),
                "больше" if c.direction == "max" else "меньше"))
        select(self.tree, keep)
        self.points.set(str(p.n_points))
        self.tol.set(fmt(p.bisection_tol * 100, 10))
        self.ui_tol.set(fmt(p.ui_tol * 100, 10))
        self.pi_tol.set(fmt(p.pi_tol * 100, 10))
        self.ui_full.set(p.ui_full)
        self.pi_full.set(p.pi_full)

    def _on_select(self, _=None):
        iid = selected(self.tree)
        if not iid:
            return
        c = self.app.project.criterion(iid)
        self.vars["name"].set(c.name)
        self.vars["unit"].set(c.unit)
        self.vars["worst"].set(fmt(c.worst, c.span / 1000))
        self.vars["best"].set(fmt(c.best, c.span / 1000))

    def _read(self) -> Criterion:
        c = Criterion(self.vars["name"].get().strip(), self.vars["unit"].get().strip(),
                      parse_float(self.vars["worst"].get(), "Наихудшее"),
                      parse_float(self.vars["best"].get(), "Наилучшее"))
        c.validate()
        return c

    def _has_context_answers(self) -> bool:
        p = self.app.project
        return bool(p.ui or p.pi or p.weight_answers or p.p_ref)

    def _add(self):
        try:
            c = self._read()
            if self._has_context_answers() and not messagebox.askyesno(
                    "MAUT", "Новый критерий меняет вопросы с «прочими критериями». Проверки независимости "
                            "и веса будут сброшены. Продолжить?"):
                return
            self.app.project.add_criterion(c)
        except MautError as e:
            show_error(e)
            return
        self.app.changed()
        select(self.tree, c.name)

    def _update(self):
        iid = selected(self.tree)
        if not iid:
            show_error(MautError("Выберите критерий в таблице"))
            return
        try:
            c = self._read()
            old = self.app.project.criterion(iid)
            if (old.worst, old.best) != (c.worst, c.best) and not messagebox.askyesno(
                    "MAUT", "Изменение диапазона сбросит ответы ЛПР по этому критерию, проверки "
                            "независимости и веса. Продолжить?"):
                return
            self.app.project.update_criterion(iid, c)
        except MautError as e:
            show_error(e)
            return
        self.app.changed()
        select(self.tree, c.name)

    def _delete(self):
        iid = selected(self.tree)
        if not iid:
            return
        if not messagebox.askyesno("MAUT", f"Удалить критерий «{iid}» и все ответы по нему?"):
            return
        self.app.project.remove_criterion(iid)
        self.app.changed()

    def _apply(self):
        p = self.app.project
        try:
            tol = parse_float(self.tol.get(), "Точность диалога") / 100
            ui_tol = parse_float(self.ui_tol.get(), "Допуск по полезности") / 100
            pi_tol = parse_float(self.pi_tol.get(), "Допуск по предпочтению") / 100
            if not 0 < tol < 0.5:
                raise MautError("Точность диалога: от 0 до 50 % диапазона")
            if not (0 <= ui_tol < 1 and 0 <= pi_tol < 1):
                raise MautError("Допуски проверок: от 0 до 100 %")
            levels = levels_for_points(int(self.points.get()))
        except (MautError, ValueError) as e:
            show_error(e)
            return
        if levels < p.levels and not messagebox.askyesno(
                "MAUT", "При меньшем числе точек лотереи глубоких уровней будут удалены. Продолжить?"):
            return
        p.set_levels(levels)
        p.bisection_tol, p.ui_tol, p.pi_tol = tol, ui_tol, pi_tol
        p.ui_full, p.pi_full = self.ui_full.get(), self.pi_full.get()
        self.app.changed()


# ======================================================================= лотереи


def lottery_spec(p, name: str, row: dict, context: str) -> dict:
    """Вопрос об эквиваленте определённости лотереи (общий для шагов 2 и 3)."""
    c = p.criterion(name)
    lo, hi = row["x_lo"], row["x_hi"]
    worse, better = (lo, hi) if c.t(lo) < c.t(hi) else (hi, lo)
    others = p.others(name)
    level = "наилучших" if context == "best" else "наихудших"
    ctx = ""
    if others:
        ctx = f"Считайте, что по остальным критериям — значения на {level} уровнях: " + ", ".join(
            f"{o.name} = {v(o, o.best if context == 'best' else o.worst)}" for o in others)

    def validate(x):
        if not c.is_between(x, lo, hi):
            raise MautError(f"Эквивалент должен лежать строго между {v(c, lo)} и {v(c, hi)}")

    return {
        "title": f"«{name}»: эквивалент определённости лотереи (U = {fmt(row['u'], 1)})",
        "context": ctx,
        "worse": worse, "better": better, "tol": p.bisection_tol * c.span, "quantum": quantum(c.span),
        "fmt": lambda x: v(c, x),
        "prompt": f"Какое гарантированное значение «{name}» для вас равноценно лотерее "
                  f"«50 % — {v(c, lo)}, 50 % — {v(c, hi)}»? Введите число строго между ними:",
        "validate": validate,
        "option_x": lambda x: f"Гарантированно {v(c, x)}",
        "option_ref": f"Лотерея: 50 % — {v(c, lo)}, 50 % — {v(c, hi)}",
        "draw": lambda cv, x: draw_lottery(cv, v(c, lo), v(c, hi),
                                           "CE = ?" if x is None else f"гарантированно {v(c, x)}?"),
    }


class CurvesTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb, padding=8)
        self.app = app
        left = ttk.Frame(self)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Критерий", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.crit = make_tree(left, [("name", "Критерий", 170), ("st", "Точек", 60)], height=14)
        self.crit.frame.pack(fill="y", expand=True)
        self.crit.bind("<<TreeviewSelect>>", lambda _: self._show_criterion())

        mid = ttk.Frame(self)
        mid.pack(side="left", fill="both", expand=True, padx=10)
        ttk.Label(mid, text="Лотереи (по остальным критериям — наилучшие значения)",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.lots = make_tree(mid, [("n", "№", 34), ("u", "U", 54), ("lot", "Лотерея 50/50", 210),
                                    ("ce", "Эквивалент", 110), ("mode", "Режим", 110),
                                    ("q", "Вопросов", 70)], height=7)
        self.lots.frame.pack(fill="x")
        self.lots.bind("<<TreeviewSelect>>", lambda _: self._show_lottery())
        self.panel = QuestionPanel(mid)
        self.panel.pack(fill="both", expand=True, pady=8)

        right = ttk.Frame(self)
        right.pack(side="left", fill="y")
        self.fig, self.canvas = plot_frame(right, (4.4, 3.6))
        self.canvas.get_tk_widget().pack()
        self.hint = ttk.Label(right, text="", wraplength=420, justify="left", foreground="#555")
        self.hint.pack(anchor="w", pady=6)

    def refresh(self):
        p = self.app.project
        keep = selected(self.crit)
        self.crit.delete(*self.crit.get_children())
        for c in p.criteria:
            n = len(p.known_points(c.name))
            self.crit.insert("", "end", iid=c.name, values=(c.name, f"{n} из {p.n_points}"))
        if not keep and p.criteria:
            keep = p.criteria[0].name
        select(self.crit, keep)
        self._show_criterion()

    def _crit_name(self):
        return selected(self.crit)

    def _show_criterion(self, next_lottery: bool = True):
        p = self.app.project
        name = self._crit_name()
        keep = selected(self.lots)
        self.lots.delete(*self.lots.get_children())
        self._plot()
        if not name:
            self.panel.clear("Добавьте критерии на первой вкладке")
            return
        c = p.criterion(name)
        rows = p.lotteries(name)
        for r in rows:
            rec = r["record"]
            lot = f"{v(c, r['x_lo'])} / {v(c, r['x_hi'])}" if r["available"] else "ждёт предыдущих"
            mode = ""
            if rec:
                modes = {a.mode for a in r["attempts"]}
                mode = "оба" if len(modes) > 1 else ("прямой" if rec.mode == "direct" else "диалог")
            self.lots.insert("", "end", iid=str(r["index"]), values=(
                r["index"] + 1, fmt(r["u"], 1), lot, v(c, rec.value) if rec else "",
                mode, rec.questions if rec else ""))
        if next_lottery:
            todo = [r for r in rows if r["available"] and r["record"] is None]
            keep = str(todo[0]["index"]) if todo else (keep or "0")
        select(self.lots, keep)
        self._show_lottery()

    def _show_lottery(self):
        p = self.app.project
        name, iid = self._crit_name(), selected(self.lots)
        if not name or iid is None:
            self.panel.clear()
            return
        row = p.lotteries(name)[int(iid)]
        if not row["available"]:
            self.panel.clear("Эта лотерея опирается на точки, которые ещё не найдены: "
                             "сначала проведите лотереи выше в таблице")
            return
        self.panel.set_spec(lottery_spec(p, name, row, "best"), lambda recs: self._done(name, row, recs))

    def _done(self, name, row, recs):
        p = self.app.project
        cleared = []
        for r in recs:
            cleared += p.set_ce(name, row["u"], r)
        if cleared:
            messagebox.showinfo("MAUT", "Точка изменилась, поэтому сброшены лотереи, построенные на ней: U = " +
                                ", ".join(fmt(u, 1) for u in sorted(set(cleared))))
        self.app.changed()

    def _plot(self):
        p = self.app.project
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        name = self._crit_name()
        if not name:
            self.canvas.draw_idle()
            return
        c = p.criterion(name)
        pts = sorted(p.known_points(name).items())
        us = [u for u, _ in pts]
        xs = [x for _, x in pts]
        ax.plot(xs, us, "-o", color="#1f5fa8", lw=1.8, ms=5)
        for x, u in zip(xs, us):
            if 0 < u < 1:
                ax.vlines(x, 0, u, colors="#999", linestyles=":", lw=0.8)
                ax.hlines(u, c.worst, x, colors="#999", linestyles=":", lw=0.8)
        ax.set_xlim(c.worst, c.best)
        ax.set_ylim(0, 1.05)
        ax.set_xlabel(f"{name}, {c.unit}" if c.unit else name)
        ax.set_ylabel(f"U({name})")
        ax.set_title("Функция полезности")
        ax.grid(alpha=0.3)
        self.canvas.draw_idle()
        done = len(pts) == p.n_points
        self.hint.config(text=(
            "Кривая построена полностью." if done else
            f"Найдено точек: {len(pts)} из {p.n_points}. Между точками функция линейная.") +
            " Ось X идёт от наихудшего значения к наилучшему, как на рисунке в методичке.")


# ======================================================================= независимость


class IndependenceTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb, padding=8)
        self.app = app
        inner = self.inner = ttk.Notebook(self)
        inner.pack(fill="both", expand=True)

        # ---- по полезности
        ui = ttk.Frame(inner, padding=6)
        inner.add(ui, text="Независимость по полезности")
        top = ttk.Frame(ui)
        top.pack(fill="x")
        ttk.Label(top, wraplength=1150, justify="left", text=(
            "Та же лотерея, что и при построении функции полезности, но теперь по остальным критериям "
            "наихудшие значения. Если эквиваленты совпадают (в пределах допуска), критерий не зависит "
            "по полезности от остальных.")).pack(anchor="w")
        body = ttk.Frame(ui)
        body.pack(fill="both", expand=True, pady=6)
        # панель вопроса пакуется первой, чтобы при узком окне сжималась таблица, а не она
        self.ui_panel = QuestionPanel(body)
        self.ui_panel.title.config(wraplength=560)
        self.ui_panel.context.config(wraplength=560)
        self.ui_panel.pack(side="right", fill="both", padx=(10, 0))
        lf = ttk.Frame(body)
        lf.pack(side="left", fill="both", expand=True)
        self.ui_tree = make_tree(lf, [("c", "Критерий", 120), ("u", "U", 45), ("lot", "Лотерея", 140),
                                      ("b", "CE (прочие лучшие)", 120), ("w", "CE (прочие худшие)", 120),
                                      ("d", "Разница", 65), ("r", "Итог", 40)], height=9)
        self.ui_tree.frame.pack(fill="both", expand=True)
        self.ui_tree.bind("<<TreeviewSelect>>", lambda _: self._ui_select())
        ttk.Button(lf, text="Сбросить ответ в выбранной строке", command=self._ui_reset).pack(anchor="w", pady=(4, 0))
        self.ui_summary = ttk.Label(lf, text="", justify="left", wraplength=640)
        self.ui_summary.pack(anchor="w", pady=6)

        # ---- по предпочтению
        pi = ttk.Frame(inner, padding=6)
        inner.add(pi, text="Независимость по предпочтению")
        top = ttk.Frame(pi)
        top.pack(fill="x")
        ttk.Label(top, text="Опорный (самый важный) критерий:").pack(side="left")
        self.ref = ttk.Combobox(top, state="readonly", width=24)
        self.ref.pack(side="left", padx=6)
        self.ref.bind("<<ComboboxSelected>>", lambda _: self._set_ref())
        ttk.Label(pi, wraplength=1150, justify="left", text=(
            "Для пары критериев ищется точка безразличия при наилучших, затем при наихудших значениях "
            "прочих критериев. Если точки совпадают (в пределах допуска), пара не зависит по "
            "предпочтению от прочих критериев. В ячейке — более важный критерий пары и точка "
            "безразличия K на его шкале.")).pack(anchor="w", pady=4)
        body = ttk.Frame(pi)
        body.pack(fill="both", expand=True)
        self.pair = PairPanel(body)
        self.pair.pack(side="right", fill="both", padx=(10, 0))
        lf = ttk.Frame(body)
        lf.pack(side="left", fill="both", expand=True)
        self.pi_tree = make_tree(lf, [("p", "Пара", 190), ("b", "Прочие лучшие", 170),
                                      ("w", "Прочие худшие", 170), ("d", "Разница", 65), ("r", "Итог", 40)],
                                 height=8)
        self.pi_tree.frame.pack(fill="both", expand=True)
        self.pi_tree.bind("<<TreeviewSelect>>", lambda _: self._pi_select())
        cf = ttk.Frame(lf)
        cf.pack(anchor="w", pady=6)
        ttk.Label(cf, text="Прочие критерии:").pack(side="left")
        self.ctx = tk.StringVar(value="best")
        ttk.Radiobutton(cf, text="наилучшие", value="best", variable=self.ctx,
                        command=self._pi_select_ctx).pack(side="left", padx=4)
        ttk.Radiobutton(cf, text="наихудшие", value="worst", variable=self.ctx,
                        command=self._pi_select_ctx).pack(side="left")
        ttk.Button(lf, text="Сбросить ответы по выбранной паре", command=self._pi_reset).pack(anchor="w", pady=(0, 4))
        self.pi_summary = ttk.Label(lf, text="", justify="left", wraplength=640)
        self.pi_summary.pack(anchor="w")

    def refresh(self):
        self._ui_refresh()
        self._pi_refresh()

    # ---- по полезности

    def _ui_refresh(self):
        p = self.app.project
        keep = selected(self.ui_tree)
        self.ui_tree.delete(*self.ui_tree.get_children())
        lines = []
        first_todo = None
        for c in p.criteria:
            for r in p.ui_rows(c.name):
                iid = f"{c.name}|{r['u']}"
                lot = f"{v(c, r['x_lo'])} / {v(c, r['x_hi'])}" if r["x_lo"] is not None else ""
                d = pct(r["diff"]) if r["diff"] is not None else ""
                self.ui_tree.insert("", "end", iid=iid, values=(
                    c.name, fmt(r["u"], 1), lot, v(c, r["ce_best"]), v(c, r["ce_worst"]), d, mark(r["ok"])))
                if first_todo is None and r["available"] and r["ce_worst"] is None:
                    first_todo = iid
            st = p.ui_status(c.name)
            lines.append(f"{mark(st)} {c.name}: " + {True: "не зависит по полезности от прочих",
                                                        False: "ЗАВИСИТ по полезности от прочих",
                                                        None: "проверка не закончена"}[st])
        tail = f"Допуск: {pct(p.ui_tol)} диапазона. " + (
            "Проверяются все лотереи." if p.ui_full else "Приближённая проверка — по первой лотерее.")
        if any(p.ui_status(c.name) is False for c in p.criteria):
            tail += ("\nПри нарушении аддитивная и мультипликативная модели строго не применимы: "
                     "методичка предлагает разбить критерии на группы или переформулировать задачу.")
        self.ui_summary.config(text="\n".join(lines + [tail]))
        kids = self.ui_tree.get_children()
        select(self.ui_tree, first_todo or (keep if keep in kids else (kids[0] if kids else None)))
        self._ui_select()

    def _ui_select(self):
        p = self.app.project
        iid = selected(self.ui_tree)
        if not iid:
            self.ui_panel.clear("Выберите строку в таблице")
            return
        name, u = iid.rsplit("|", 1)
        u = float(u)
        row = next(r for r in p.ui_rows(name) if abs(r["u"] - u) < 1e-12)
        if not row["available"]:
            self.ui_panel.clear("Сначала проведите эту лотерею на вкладке «Функции полезности»")
            return
        self.ui_panel.set_spec(lottery_spec(p, name, row, "worst"), lambda recs: self._ui_done(name, u, recs))

    def _ui_reset(self):
        iid = selected(self.ui_tree)
        if not iid:
            return
        name, u = iid.rsplit("|", 1)
        if not self.app.project.clear_ui(name, float(u)):
            show_error(MautError("В этой строке ещё нет проверочного ответа"))
            return
        self.app.changed()

    def _ui_done(self, name, u, recs):
        for r in recs:
            self.app.project.set_ui(name, u, r)
        self.app.changed()

    # ---- по предпочтению

    def _set_ref(self):
        self.app.project.set_ref(self.ref.get() or None)
        self.app.changed()

    def _pi_refresh(self):
        p = self.app.project
        self.ref["values"] = p.names()
        self.ref.set(p.ref or "")
        keep = selected(self.pi_tree)
        self.pi_tree.delete(*self.pi_tree.get_children())
        pairs = p.pi_pairs()
        first_todo = None
        for a, b in pairs:
            row = p.pi_row(a, b)
            iid = f"{a}|{b}"
            d = pct(row["diff"]) if row["diff"] is not None else ""
            self.pi_tree.insert("", "end", iid=iid, values=(
                f"{a} — {b}", self._ans(row["best"]), self._ans(row["worst"]), d, mark(row["ok"])))
            if first_todo is None and not (row["best"] and row["worst"]):
                first_todo = iid
        if len(p.criteria) < 3:
            txt = "Критериев меньше трёх: «прочих» критериев нет, условие выполняется тривиально."
        else:
            rows = [p.pi_row(a, b) for a, b in pairs]
            txt = ("Проверяются все пары. " if p.pi_full or p.ref is None else
                   "Приближённая проверка — пары с опорным критерием. ") + f"Допуск: {pct(p.pi_tol)}. "
            bad = [f"{r['a']} — {r['b']}: {r['why']}" for r in rows if r["ok"] is False]
            st = p.pi_status()
            txt += {True: "Условие выполнено.", False: "Условие нарушено:\n" + "\n".join(bad),
                    None: "Проверка не закончена."}[st]
            if p.ref is None:
                txt += "\nОпорный критерий не выбран — проверяются все пары."
        self.pi_summary.config(text=txt)
        kids = self.pi_tree.get_children()
        select(self.pi_tree, first_todo or (keep if keep in kids else (kids[0] if kids else None)))
        if first_todo:
            # следующий непройденный контекст этой пары
            row = p.pi_row(*first_todo.split("|"))
            self.ctx.set("worst" if row["best"] else "best")
        self._pi_select()

    def _ans(self, ans) -> str:
        if ans is None:
            return ""
        if ans.corner == "equal":
            return "A ~ B"
        c = self.app.project.criterion(ans.scale)
        return f"{ans.scale}: K = {v(c, ans.record.value)}"

    def _pi_select_ctx(self):
        self._pi_select()

    def _pi_select(self):
        p = self.app.project
        iid = selected(self.pi_tree)
        if not iid:
            self.pair.clear("Выберите пару в таблице" if p.pi_pairs() else "")
            return
        a, b = iid.split("|")
        ctx = self.ctx.get()
        self.pair.set_pair(p, a, b, ctx, lambda ans: self._pi_done(ans),
                           answered=p.pi_answer(a, b, ctx) is not None)

    def _pi_reset(self):
        iid = selected(self.pi_tree)
        if not iid:
            return
        a, b = iid.split("|")
        if not messagebox.askyesno("MAUT", f"Сбросить ответы по паре «{a} — {b}» (оба уровня прочих критериев)?"):
            return
        if not self.app.project.clear_pi(a, b):
            show_error(MautError("По этой паре ещё нет ответов"))
            return
        self.app.changed()

    def _pi_done(self, ans):
        try:
            self.app.project.set_pi(ans)
        except MautError as e:
            show_error(e)
            return
        self.app.changed()


# ======================================================================= веса


def _check_p(x: float) -> None:
    if not 0 < x < 1:
        raise MautError("p должна быть в интервале (0, 1)")


class WeightsTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb, padding=8)
        self.app = app
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Опорный (самый важный) критерий:").pack(side="left")
        self.ref = ttk.Combobox(top, state="readonly", width=24)
        self.ref.pack(side="left", padx=6)
        self.ref.bind("<<ComboboxSelected>>", lambda _: self._set_ref())
        ttk.Label(top, text="   Модель:").pack(side="left")
        self.model = tk.StringVar(value="additive")
        ttk.Radiobutton(top, text="аддитивная", value="additive", variable=self.model,
                        command=self._set_model).pack(side="left", padx=4)
        ttk.Radiobutton(top, text="мультипликативная", value="multiplicative", variable=self.model,
                        command=self._set_model).pack(side="left")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=6)
        right = ttk.Frame(body)
        right.pack(side="right", fill="y", padx=(10, 0))
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, wraplength=640, justify="left", text=(
            "Для каждого критерия Cj ищется точка безразличия на плоскости (опорный, Cj). "
            "Прочие критерии — на наихудших значениях: так равенство верно и для мультипликативной "
            "модели.")).pack(anchor="w")
        self.tree = make_tree(left, [("pair", "Пара (опорный — Cj)", 195), ("ans", "Важнее в паре", 120),
                                     ("k", "Точка K", 160), ("r", "wj / w_оп", 105), ("w", "Вес", 50)], height=6)
        self.tree.frame.pack(fill="x", pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._select())
        bf = ttk.Frame(left)
        bf.pack(anchor="w")
        self.reset_btn = ttk.Button(bf, text="Сбросить ответ по выбранной паре", command=self._reset)
        self.reset_btn.pack(side="left")
        ttk.Label(bf, text="  Удалить сам критерий можно на вкладке «1. Критерии».",
                  foreground="#555").pack(side="left")
        self.pair = PairPanel(left)
        self.pair.pack(fill="both", expand=True)

        self.fig, self.canvas = plot_frame(right, (4.4, 2.6))
        self.canvas.get_tk_widget().pack()
        self.info = ttk.Label(right, text="", wraplength=440, justify="left")
        self.info.pack(anchor="w", pady=4)
        self.mult = ttk.LabelFrame(right, text="Мультипликативная модель: вероятность p", padding=6)
        self.mult.pack(fill="x")
        self.p_panel = QuestionPanel(self.mult, canvas_size=(420, 120))
        self.p_panel.title.config(wraplength=420)
        self.p_panel.context.config(wraplength=420)
        self.p_panel.pack(fill="x")

    def refresh(self):
        p = self.app.project
        self.ref["values"] = p.names()
        self.ref.set(p.ref or "")
        self.model.set(p.model)
        keep = selected(self.tree)
        self.tree.delete(*self.tree.get_children())
        try:
            w = p.weights()
        except MautError as e:
            w = None
            err = str(e)
        first_todo = None
        if p.ref:
            for c in p.criteria:
                if c.name == p.ref:
                    # опорный критерий ни с чем не сравнивается: его вес — база, wоп / wоп = 1
                    self.tree.insert("", "end", iid=c.name, values=(
                        f"{c.name} (опорный)", "—", "—", "1", fmt(w[c.name], 1) if w else ""))
                    continue
                pair = f"{p.ref} — {c.name}"
                ans = p.weight_answers.get(c.name)
                if ans is None:
                    vals = (pair, "не сравнивали", "", "", "")
                    first_todo = first_todo or c.name
                else:
                    who = {"a": f"{p.ref} (A)", "b": f"{c.name} (B)", "equal": "одинаково"}[ans.corner]
                    k = ""
                    if ans.record:
                        k = f"{ans.scale} = {v(p.criterion(ans.scale), ans.record.value)}"
                    try:
                        r = fmt(ans.ratio({ans.scale: p.utility(ans.scale)} if ans.scale else {}), 1)
                    except MautError:
                        r = f"нужна U({ans.scale})"
                    vals = (pair, who, k, r, fmt(w[c.name], 1) if w else "")
                self.tree.insert("", "end", iid=c.name, values=vals)
        select(self.tree, first_todo or keep)
        self._select()
        self._plot(w)
        if not p.ref:
            info = "Выберите опорный критерий — тот, переход которого от худшего значения к лучшему " \
                   "для ЛПР ценнее всего."
        elif w:
            order = " > ".join(f"w({n})" for n in sorted(w, key=lambda n: -w[n]))
            info = "Веса нормированы к сумме 1. Порядок важности: " + order
            if any(a.corner == "b" for a in p.weight_answers.values()):
                info += "\nЕсть критерий важнее опорного — опорным лучше выбрать его (веса от этого не меняются)."
        else:
            info = "Веса пока не посчитаны. " + err
            need = [a.scale for a in p.weight_answers.values()
                    if a.corner == "b" and not p.curve_complete(a.scale)]
            if need:
                info += (f"\nВ паре «{p.ref} — {need[0]}» важнее оказался «{need[0]}», поэтому вес "
                         f"считается по его функции полезности: wоп = wj·Uj(K). Постройте U({need[0]}) "
                         f"на вкладке «2. Функции полезности» или выберите опорным «{need[0]}».")
        self.info.config(text=info)
        self._p_refresh()

    def _plot(self, w):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        if w:
            names = list(w)
            ax.barh(names, [w[n] for n in names], color="#1f5fa8")
            for i, n in enumerate(names):
                ax.text(w[n] + 0.01, i, fmt(w[n], 1), va="center")
            ax.set_xlim(0, max(w.values()) * 1.25)
            ax.invert_yaxis()
        else:
            ax.text(0.5, 0.5, "Веса ещё не найдены", ha="center", va="center", color="#777",
                    transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
        ax.set_title("Веса критериев")
        ax.grid(axis="x", alpha=0.3)
        self.canvas.draw_idle()

    def _set_ref(self):
        p = self.app.project
        if p.weight_answers and not messagebox.askyesno("MAUT", "Смена опорного критерия сбросит найденные "
                                                                 "точки безразличия для весов. Продолжить?"):
            self.ref.set(p.ref or "")
            return
        p.set_ref(self.ref.get() or None)
        self.app.changed()

    def _set_model(self):
        self.app.project.model = self.model.get()
        self.app.changed()

    def _select(self):
        p = self.app.project
        iid = selected(self.tree)
        if not p.ref:
            self.pair.clear("Сначала выберите опорный критерий")
            return
        if not iid or iid == p.ref:
            self.pair.clear("Выберите в таблице критерий, кроме опорного: опорный ни с чем не "
                            "сравнивается, остальные веса считаются относительно него")
            return
        self.pair.set_pair(p, p.ref, iid, "worst", self._done, answered=iid in p.weight_answers)

    def _reset(self):
        p = self.app.project
        iid = selected(self.tree)
        if not iid or iid == p.ref or iid not in p.weight_answers:
            show_error(MautError("Выберите в таблице критерий, по которому уже есть ответ"))
            return
        if not messagebox.askyesno("MAUT", f"Сбросить ответ по паре «{p.ref} — {iid}»?"):
            return
        p.clear_weight_answer(iid)
        self.app.changed()

    def _done(self, ans):
        try:
            self.app.project.set_weight_answer(ans)
        except MautError as e:
            show_error(e)
            return
        self.app.changed()

    def _p_refresh(self):
        p = self.app.project
        if p.model != "multiplicative":
            self.p_panel.clear("Выберите мультипликативную модель, чтобы задать p")
            return
        if not p.ref:
            self.p_panel.clear("Сначала выберите опорный критерий")
            return
        ref = p.criterion(p.ref)
        sure = f"Гарантированно: {ref.name} — наилучшее, прочие — наихудшие"
        spec = {
            "title": "При какой вероятности p лотерея равноценна гарантированному варианту?",
            "context": sure + ". Лотерея: с вероятностью p все критерии наилучшие, с вероятностью "
                              "1 − p все наихудшие. Тогда k_оп = p, kj = p·(wj / w_оп).",
            "worse": 0.0, "better": 1.0, "tol": p.bisection_tol, "quantum": 0.001,
            "fmt": lambda x: "p = " + f"{x:.3f}".replace(".", ","),
            "prompt": "Вероятность p (от 0 до 1):",
            "validate": _check_p,
            "option_x": lambda x: f"Лотерея: {pct(x)} — все лучшие, {pct(1 - x)} — все худшие",
            "option_ref": sure,
            "draw": lambda cv, x: draw_lottery(cv, "все наилучшие", "все наихудшие",
                                               "~ гарантированный вариант",
                                               "p" if x is None else f"{x:.2f}".replace(".", ","),
                                               "1 − p" if x is None else f"{1 - x:.2f}".replace(".", ",")),
        }
        if self.p_panel.spec is None or self.p_panel.start_btn.instate(["!disabled"]):
            self.p_panel.set_spec(spec, self._p_done)
        try:
            ks = p.scaling()
            k = p.k()
            txt = "ki: " + ", ".join(f"{n} = {fmt(x, 1)}" for n, x in ks.items()) + \
                  f"; Σki = {fmt(sum(ks.values()), 1)}; k = {fmt(k, 0.1)}"
            if k == 0:
                txt += " (модель аддитивная)"
            self.p_panel.context.config(text=spec["context"] + "\n" + txt)
        except MautError as e:
            if p.p_ref:
                self.p_panel.context.config(text=spec["context"] + "\n" + str(e))

    def _p_done(self, recs):
        for r in recs:
            self.app.project.set_p(r)
        self.app.changed()


# ======================================================================= альтернативы


class AlternativesTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb, padding=8)
        self.app = app
        self._cols = None
        top = ttk.Frame(self)
        top.pack(fill="both", expand=True)
        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Альтернативы", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.tree_holder = ttk.Frame(left)
        self.tree_holder.pack(fill="x")
        self.form = ttk.LabelFrame(left, text="Альтернатива", padding=6)
        self.form.pack(fill="x", pady=6)
        ttk.Label(left, text="Результат", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(6, 0))
        self.res_holder = ttk.Frame(left)
        self.res_holder.pack(fill="both", expand=True)
        self.msg = ttk.Label(left, text="", wraplength=700, justify="left")
        self.msg.pack(anchor="w", pady=4)
        right = ttk.Frame(top)
        right.pack(side="left", fill="y", padx=(10, 0))
        self.fig, self.canvas = plot_frame(right, (4.8, 4.2))
        self.canvas.get_tk_widget().pack()

    def _build(self):
        p = self.app.project
        names = p.names()
        if names == self._cols:
            return
        self._cols = names
        for w in self.tree_holder.winfo_children() + self.form.winfo_children() + self.res_holder.winfo_children():
            w.destroy()
        cols = [("name", "Альтернатива", 160)] + [(f"c{i}", n, 110) for i, n in enumerate(names)]
        self.tree = make_tree(self.tree_holder, cols, height=6)
        self.tree.frame.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._on_select())
        self.vars = {"name": tk.StringVar()}
        ttk.Label(self.form, text="Название").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.form, textvariable=self.vars["name"], width=20).grid(row=1, column=0, padx=(0, 8))
        for i, c in enumerate(p.criteria):
            self.vars[c.name] = tk.StringVar()
            ttk.Label(self.form, text=f"{c.name}, {c.unit}" if c.unit else c.name).grid(row=0, column=i + 1, sticky="w")
            ttk.Entry(self.form, textvariable=self.vars[c.name], width=12).grid(row=1, column=i + 1, padx=(0, 8))
        bf = ttk.Frame(self.form)
        bf.grid(row=2, column=0, columnspan=len(names) + 1, sticky="w", pady=(6, 0))
        ttk.Button(bf, text="Добавить", command=self._add).pack(side="left")
        ttk.Button(bf, text="Изменить выбранную", command=self._update).pack(side="left", padx=6)
        ttk.Button(bf, text="Удалить выбранную", command=self._delete).pack(side="left")
        rcols = [("rank", "Ранг", 50), ("name", "Альтернатива", 150)] + \
                [(f"u{i}", f"U({n})", 90) for i, n in enumerate(names)] + [("U", "U", 80), ("U2", "", 110)]
        self.res = make_tree(self.res_holder, rcols, height=7)
        self.res.frame.pack(fill="both", expand=True)

    def refresh(self):
        self._build()
        p = self.app.project
        keep = selected(self.tree)
        self.tree.delete(*self.tree.get_children())
        for i, a in enumerate(p.alternatives):
            self.tree.insert("", "end", iid=str(i), values=[a.name] + [
                fmt(a.values[c.name], c.span) if c.name in a.values else "" for c in p.criteria])
        select(self.tree, keep)
        self._evaluate()

    def _read(self) -> Alternative:
        p = self.app.project
        name = self.vars["name"].get().strip()
        if not name:
            raise MautError("Введите название альтернативы")
        return Alternative(name, {c.name: parse_float(self.vars[c.name].get(), c.name) for c in p.criteria})

    def _on_select(self):
        iid = selected(self.tree)
        if iid is None:
            return
        a = self.app.project.alternatives[int(iid)]
        self.vars["name"].set(a.name)
        for c in self.app.project.criteria:
            self.vars[c.name].set(fmt(a.values.get(c.name, 0), c.span / 100))

    def _add(self):
        try:
            a = self._read()
        except MautError as e:
            show_error(e)
            return
        self.app.project.alternatives.append(a)
        self.app.changed()

    def _update(self):
        iid = selected(self.tree)
        if iid is None:
            show_error(MautError("Выберите альтернативу в таблице"))
            return
        try:
            self.app.project.alternatives[int(iid)] = self._read()
        except MautError as e:
            show_error(e)
            return
        self.app.changed()

    def _delete(self):
        iid = selected(self.tree)
        if iid is None:
            return
        del self.app.project.alternatives[int(iid)]
        self.app.changed()

    def _evaluate(self):
        p = self.app.project
        self.res.delete(*self.res.get_children())
        self.fig.clear()
        try:
            res = p.evaluate()
        except MautError as e:
            self.msg.config(text="Расчёт пока невозможен: " + str(e), foreground="#a40")
            self.canvas.draw_idle()
            return
        extra = None
        if res["model"] == "multiplicative":
            self.res.heading("U2", text="U аддитивная")
            extra = {r["name"]: r["U"] for r in p.evaluate(model="additive")["rows"]}
        else:
            self.res.heading("U2", text="")
        for r in sorted(res["rows"], key=lambda r: r["rank"]):
            self.res.insert("", "end", values=[r["rank"], r["name"]] + [fmt(r["u"][n], 1) for n in p.names()] +
                            [fmt(r["U"], 0.1), fmt(extra[r["name"]], 0.1) if extra else ""])
        best = min(res["rows"], key=lambda r: r["rank"])
        txt = f"Модель: {'аддитивная' if res['model'] == 'additive' else 'мультипликативная'}. " \
              f"Лучшая альтернатива: «{best['name']}», U = {fmt(best['U'], 0.1)}."
        if res["model"] == "multiplicative":
            txt += f" k = {fmt(res['k'], 0.1)}."
        if res["warnings"]:
            txt += "\n" + "\n".join(res["warnings"])
        viol = [c.name for c in p.criteria if p.ui_status(c.name) is False]
        if viol or p.pi_status() is False:
            txt += "\nВнимание: условия независимости нарушены, результат следует считать приближённым."
        self.msg.config(text=txt, foreground="black")
        self._plot(res)

    def _plot(self, res):
        p = self.app.project
        ax = self.fig.add_subplot(111)
        rows = sorted(res["rows"], key=lambda r: r["rank"])
        names = [r["name"] for r in rows]
        if res["model"] == "additive":
            left = [0.0] * len(rows)
            colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
            for i, n in enumerate(p.names()):
                vals = [r["contrib"][n] for r in rows]
                ax.barh(names, vals, left=left, color=colors[i % len(colors)], label=n)
                left = [l + x for l, x in zip(left, vals)]
            ax.legend(fontsize=8, loc="lower right")
            ax.set_title("Многокритериальная полезность\n(вклад критериев wi·Ui)")
        else:
            ax.barh(names, [r["U"] for r in rows], color="#1f5fa8")
            ax.set_title("Многокритериальная полезность")
        for i, r in enumerate(rows):
            ax.text(r["U"] + 0.01, i, fmt(r["U"], 0.1), va="center", fontsize=9)
        ax.set_xlim(0, 1.15)
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.3)
        self.canvas.draw_idle()


# ======================================================================= сравнение режимов


class CompareTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb, padding=8)
        self.app = app
        ttk.Label(self, wraplength=1150, justify="left", text=(
            "Здесь собраны вопросы, на которые ЛПР ответил обоими режимами (режим «Оба (сравнение)» "
            "в лотереях и при вводе p). Разница — в процентах диапазона критерия.")).pack(anchor="w")
        self.tree = make_tree(self, [("w", "Вопрос", 260), ("d", "Прямой ввод", 120), ("b", "Диалог", 120),
                                     ("diff", "Разница", 80), ("qd", "Вопросов (прямой)", 120),
                                     ("qb", "Вопросов (диалог)", 120), ("td", "Время, с (прямой)", 120),
                                     ("tb", "Время, с (диалог)", 120)], height=14)
        self.tree.frame.pack(fill="both", expand=True, pady=6)
        self.summary = ttk.Label(self, text="", justify="left")
        self.summary.pack(anchor="w")

    def refresh(self):
        p = self.app.project
        self.tree.delete(*self.tree.get_children())
        rows = p.mode_comparisons()

        def t(r):
            return "" if r.seconds is None else fmt(r.seconds, 10)

        def val(r, label):
            if label.startswith("вероятность"):
                return f"{r.value:.3f}".replace(".", ",")
            name = label.split(":")[0]
            return v(p.criterion(name), r.value)

        for r in rows:
            self.tree.insert("", "end", values=(
                r["what"], val(r["direct"], r["what"]), val(r["bisection"], r["what"]), pct(r["diff"]),
                r["direct"].questions, r["bisection"].questions, t(r["direct"]), t(r["bisection"])))
        if not rows:
            self.summary.config(text="Сравнений пока нет.")
            return
        n = len(rows)
        md = sum(r["diff"] for r in rows) / n
        qb = sum(r["bisection"].questions for r in rows) / n
        secs = [(r["direct"].seconds, r["bisection"].seconds) for r in rows
                if r["direct"].seconds is not None and r["bisection"].seconds is not None]
        txt = f"Сравнений: {n}. Средняя разница ответов: {pct(md)} диапазона. " \
              f"Диалог в среднем занял {fmt(qb, 10)} вопроса против одного при прямом вводе."
        if secs:
            sd = sum(s[0] for s in secs) / len(secs)
            sb = sum(s[1] for s in secs) / len(secs)
            txt += f"\nСреднее время: прямой ввод {fmt(sd, 10)} с, диалог {fmt(sb, 10)} с."
        self.summary.config(text=txt)
