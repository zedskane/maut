"""Общие элементы окна: панель вопроса к ЛПР, панель пары критериев, рисунки."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk

from maut.elicitation import EQUAL, PREFER_REF, PREFER_X, BisectionSession, direct
from maut.model import MautError, fmt, quantum
from maut.weights import PairAnswer

MODES = (("direct", "Прямой ввод"), ("bisection", "Диалог «выше/ниже»"), ("both", "Оба (сравнение)"))


def parse_float(s: str, what: str) -> float:
    """Число из поля ввода; допускается запятая."""
    s = s.strip().replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        raise MautError(f"{what}: «{s}» не число") from None


def show_error(e: Exception) -> None:
    messagebox.showerror("MAUT", str(e))


# ------------------------------------------------------------------ рисунки


def draw_lottery(cv: tk.Canvas, lo_text: str, hi_text: str, mid_text: str,
                 p_top: str = "0,5", p_bottom: str = "0,5") -> None:
    """Лотерея как на рисунке в методичке: корень и два исхода с вероятностями."""
    cv.delete("all")
    w = int(cv["width"])
    h = int(cv["height"])
    r = 7
    x0, y0 = 30, h // 2
    x1, ya, yb = w // 2 - 30, 25, h - 25
    cv.create_line(x0, y0, x1, ya, width=1.5)
    cv.create_line(x0, y0, x1, yb, width=1.5)
    for x, y in ((x0, y0), (x1, ya), (x1, yb)):
        cv.create_oval(x - r, y - r, x + r, y + r, fill="white", width=1.5)
    cv.create_text((x0 + x1) / 2 - 10, (y0 + ya) / 2 - 10, text=p_top, anchor="e")
    cv.create_text((x0 + x1) / 2 - 10, (y0 + yb) / 2 + 10, text=p_bottom, anchor="e")
    cv.create_text(x1 + 14, ya, text=lo_text, anchor="w")
    cv.create_text(x1 + 14, yb, text=hi_text, anchor="w")
    cv.create_text(x1 + 14, y0, text=mid_text, anchor="w", fill="#1f5fa8", font=("TkDefaultFont", 10, "bold"))


def draw_plane(cv: tk.Canvas, a_name: str, b_name: str, a_ends: tuple[str, str], b_ends: tuple[str, str],
               corner: str | None, k_text: str | None, k_frac: float | None) -> None:
    """Плоскость двух критериев: по осям значения от худших к лучшим.

    A = (a лучшее, b худшее), B = (a худшее, b лучшее), K — искомая точка
    безразличия на оси того критерия, который оказался важнее.
    """
    cv.delete("all")
    w = int(cv["width"])
    h = int(cv["height"])
    ox, oy = 60, h - 38          # начало координат (худшие значения)
    ex, ey = w - 20, 16          # концы осей
    ax, ay = ex - 40, oy         # A: a лучшее, b худшее
    bx, by = ox, ey + 22         # B: a худшее, b лучшее
    cv.create_line(ox, oy, ex, oy, arrow="last")
    cv.create_line(ox, oy, ox, ey, arrow="last")
    cv.create_text(ex, oy + 22, text=f"{a_name} →", anchor="ne", fill="#555")
    cv.create_text(ox + 8, ey, text=f"↑ {b_name}", anchor="nw", fill="#555")
    cv.create_text(ox, oy + 5, text=a_ends[0], anchor="n")
    cv.create_text(ax, oy + 5, text=a_ends[1], anchor="n")
    cv.create_text(ox - 6, oy, text=b_ends[0], anchor="e")
    cv.create_text(ox - 6, by, text=b_ends[1], anchor="e")
    for x, y, t in ((ax, ay, "A"), (bx, by, "B")):
        cv.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#444")
        if t == "A":
            cv.create_text(x + 7, y - 7, text=t, anchor="sw", font=("TkDefaultFont", 10, "bold"))
        else:
            cv.create_text(x + 9, y, text=t, anchor="w", font=("TkDefaultFont", 10, "bold"))
    if corner in ("a", "b") and k_frac is not None:
        if corner == "a":
            kx, ky = ox + (ax - ox) * k_frac, oy
            src = (bx, by)
        else:
            kx, ky = ox, oy - (oy - by) * k_frac
            src = (ax, ay)
        cv.create_line(*src, kx, ky, dash=(4, 3), fill="#1f5fa8", width=1.5)
        cv.create_oval(kx - 5, ky - 5, kx + 5, ky + 5, fill="#1f5fa8", outline="#1f5fa8")
        cv.create_text(kx + 8, ky - 8, text=f"K {k_text or ''}", anchor="sw", fill="#1f5fa8")


# ------------------------------------------------------------------ панель вопроса


class QuestionPanel(ttk.Frame):
    """Опрос ЛПР по одному вопросу в выбранном режиме.

    spec — словарь:
      title       — что ищем (заголовок);
      context     — пояснение (уровни прочих критериев и т. п.);
      worse, better, tol — шкала поиска и точность диалога;
      fmt         — функция «число → текст с единицами»;
      prompt      — подпись к полю прямого ввода;
      validate    — проверка введённого числа (бросает MautError);
      option_x    — текст варианта с текущим x;
      option_ref  — текст фиксированного варианта;
      draw        — рисунок: draw(canvas, x или None) (необязательно).
    on_done(records) получает список попыток: одну, или две в режиме «Оба».
    """

    def __init__(self, master, allow_both: bool = True, canvas_size=(430, 150)):
        super().__init__(master)
        self.spec = None
        self.on_done = None
        self.active = False   # идёт опрос
        self.title = ttk.Label(self, text="", font=("TkDefaultFont", 10, "bold"), wraplength=620, justify="left")
        self.title.pack(anchor="w", fill="x")
        self.context = ttk.Label(self, text="", wraplength=620, justify="left", foreground="#555")
        self.context.pack(anchor="w", fill="x", pady=(2, 4))
        self.canvas = tk.Canvas(self, width=canvas_size[0], height=canvas_size[1], bg="white",
                                highlightthickness=1, highlightbackground="#ccc")
        self.canvas.pack(anchor="w", pady=4)
        mf = ttk.Frame(self)
        mf.pack(anchor="w", fill="x")
        ttk.Label(mf, text="Режим:").pack(side="left")
        self.mode = tk.StringVar(value="bisection")
        for val, text in MODES:
            if val == "both" and not allow_both:
                continue
            ttk.Radiobutton(mf, text=text, value=val, variable=self.mode).pack(side="left", padx=4)
        self.start_btn = ttk.Button(mf, text="Начать опрос", command=self._begin)
        self.start_btn.pack(side="left", padx=10)
        self.body = ttk.Frame(self)
        self.body.pack(anchor="w", fill="x", pady=6)
        self.clear()

    # -------------------------------------------------------------- управление

    def clear(self, text: str = "Выберите вопрос в таблице") -> None:
        self.spec = None
        self.title.config(text=text)
        self.context.config(text="")
        self.canvas.delete("all")
        self.start_btn.state(["disabled"])
        self._clear_body()

    def set_spec(self, spec: dict, on_done) -> None:
        self.spec = spec
        self.on_done = on_done
        self.title.config(text=spec["title"])
        self.context.config(text=spec.get("context", ""))
        self._draw(None)
        self.start_btn.state(["!disabled"])
        self._clear_body()

    def _clear_body(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()

    def _draw(self, x) -> None:
        if self.spec and self.spec.get("draw"):
            self.spec["draw"](self.canvas, x)

    def _begin(self) -> None:
        if not self.spec:
            return
        m = self.mode.get()
        self.queue = ["direct", "bisection"] if m == "both" else [m]
        self.records = []
        self.active = True
        self.start_btn.state(["disabled"])
        self._next()

    def _next(self) -> None:
        self._clear_body()
        if not self.queue:
            self.active = False
            self.start_btn.state(["!disabled"])
            recs, self.records = self.records, []
            self._draw(recs[-1].value)
            ttk.Label(self.body, text="Результат: " + "; ".join(
                f"{'прямой ввод' if r.mode == 'direct' else 'диалог'} — {self.spec['fmt'](r.value)}"
                f" ({r.questions} вопр.)" for r in recs), foreground="#1a7f37").pack(anchor="w")
            try:
                self.on_done(recs)
            except MautError as e:
                show_error(e)
            return
        step = self.queue.pop(0)
        self.t0 = time.monotonic()
        if step == "direct":
            self._show_direct()
        else:
            self.session = BisectionSession(self.spec["worse"], self.spec["better"], self.spec["tol"],
                                            quantum=self.spec.get("quantum", 0.0))
            self._show_question()

    def _cancel(self) -> None:
        self.active = False
        self.queue = []
        self.records = []
        self._clear_body()
        self._draw(None)
        self.start_btn.state(["!disabled"])

    # -------------------------------------------------------------- прямой ввод

    def _show_direct(self) -> None:
        self._draw(None)
        ttk.Label(self.body, text=self.spec["prompt"], wraplength=620, justify="left").pack(anchor="w")
        row = ttk.Frame(self.body)
        row.pack(anchor="w", pady=4)
        var = tk.StringVar()
        e = ttk.Entry(row, textvariable=var, width=14)
        e.pack(side="left")
        e.focus_set()

        def accept(*_):
            try:
                v = parse_float(var.get(), "Значение")
                self.spec["validate"](v)
            except MautError as err:
                show_error(err)
                return
            self.records.append(direct(v, time.monotonic() - self.t0))
            self._next()

        e.bind("<Return>", accept)
        ttk.Button(row, text="Принять", command=accept).pack(side="left", padx=6)
        ttk.Button(row, text="Отмена", command=self._cancel).pack(side="left")

    # -------------------------------------------------------------- диалог

    def _show_question(self) -> None:
        self._clear_body()
        s = self.session
        x = s.current()
        self._draw(x)
        f = self.spec["fmt"]
        lo = s.worse + s.lo * (s.better - s.worse)
        hi = s.worse + s.hi * (s.better - s.worse)
        ttk.Label(self.body, text=f"Вопрос {len(s.history) + 1}. Что вы выберете?",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(self.body, text=f"Точка безразличия сейчас между {f(lo)} и {f(hi)}",
                  foreground="#555").pack(anchor="w", pady=(0, 4))
        ttk.Button(self.body, text=self.spec["option_x"](x),
                   command=lambda: self._answer(PREFER_X)).pack(anchor="w", fill="x", pady=1)
        ttk.Button(self.body, text=self.spec["option_ref"],
                   command=lambda: self._answer(PREFER_REF)).pack(anchor="w", fill="x", pady=1)
        cf = ttk.Frame(self.body)
        cf.pack(anchor="w", pady=4)
        ttk.Button(cf, text="Равноценно", command=lambda: self._answer(EQUAL)).pack(side="left")
        b = ttk.Button(cf, text="Назад", command=self._undo)
        b.pack(side="left", padx=6)
        if not s.history:
            b.state(["disabled"])
        ttk.Button(cf, text="Отмена", command=self._cancel).pack(side="left")

    def _answer(self, ans: str) -> None:
        self.session.answer(ans)
        if self.session.done:
            self.records.append(self.session.record(time.monotonic() - self.t0))
            self._next()
        else:
            self._show_question()

    def _undo(self) -> None:
        self.session.undo()
        self._show_question()


# ------------------------------------------------------------------ панель пары


class PairPanel(ttk.Frame):
    """Пара критериев: сравнение угловых вариантов, затем поиск точки безразличия."""

    def __init__(self, master):
        super().__init__(master)
        self.head = ttk.Label(self, text="", font=("TkDefaultFont", 10, "bold"), wraplength=620, justify="left")
        self.head.pack(anchor="w", fill="x")
        self.ctx = ttk.Label(self, text="", wraplength=620, justify="left", foreground="#555")
        self.ctx.pack(anchor="w", fill="x", pady=(2, 4))
        self.canvas = tk.Canvas(self, width=430, height=160, bg="white",
                                highlightthickness=1, highlightbackground="#ccc")
        self.canvas.pack(anchor="w", pady=4)
        self.corner_frame = ttk.Frame(self)
        self.q = QuestionPanel(self, allow_both=False, canvas_size=(1, 1))
        self.q.canvas.pack_forget()
        self.q.pack(anchor="w", fill="x", pady=(6, 0))
        self.clear()

    def clear(self, text: str = "Выберите пару в таблице") -> None:
        self.head.config(text=text)
        self.ctx.config(text="")
        self.canvas.delete("all")
        self._hide_corners()
        self.q.clear("")
        self.q.pack_forget()

    def _hide_corners(self) -> None:
        # пустой фрейм в Tk не сжимается сам — убираем его из раскладки целиком
        for w in self.corner_frame.winfo_children():
            w.destroy()
        self.corner_frame.pack_forget()

    def set_pair(self, project, a: str, b: str, context: str, on_done, answered: bool = False) -> None:
        self.clear()
        self.p, self.a, self.b, self.context, self.on_done = project, a, b, context, on_done
        ca, cb = project.criterion(a), project.criterion(b)
        self.ca, self.cb = ca, cb
        others = [c for c in project.criteria if c.name not in (a, b)]
        level = "наилучшие" if context == "best" else "наихудшие"
        ctx = ""
        if others:
            ctx = "Прочие критерии зафиксированы (" + level + "): " + ", ".join(
                f"{c.name} = {fmt(c.best if context == 'best' else c.worst, c.span)} {c.unit}" for c in others)
        again = " (ответ уже есть, новый заменит его)" if answered else ""
        self.head.config(text=f"Пара «{a}» — «{b}»{again}. Шаг 1: какой вариант лучше?")
        self.ctx.config(text=ctx)
        self._redraw(None, None)
        A = f"A: {a} = {self._v(ca, ca.best)} (лучшее), {b} = {self._v(cb, cb.worst)} (худшее)"
        B = f"B: {a} = {self._v(ca, ca.worst)} (худшее), {b} = {self._v(cb, cb.best)} (лучшее)"
        self.corner_frame.pack(anchor="w", fill="x", after=self.canvas)
        ttk.Button(self.corner_frame, text=A, command=lambda: self._corner("a")).pack(anchor="w", fill="x", pady=1)
        ttk.Button(self.corner_frame, text=B, command=lambda: self._corner("b")).pack(anchor="w", fill="x", pady=1)
        ttk.Button(self.corner_frame, text="A и B равноценны",
                   command=lambda: self._corner("equal")).pack(anchor="w", pady=1)

    @staticmethod
    def _v(c, x) -> str:
        return f"{fmt(x, c.span)} {c.unit}".strip()

    def _redraw(self, corner, x) -> None:
        ca, cb = self.ca, self.cb
        frac = None
        k_text = None
        if corner in ("a", "b") and x is not None:
            c = ca if corner == "a" else cb
            frac = c.t(x)
            k_text = self._v(c, x)
        draw_plane(self.canvas, ca.name, cb.name, (fmt(ca.worst, ca.span), fmt(ca.best, ca.span)),
                   (fmt(cb.worst, cb.span), fmt(cb.best, cb.span)), corner, k_text, frac)

    def _corner(self, corner: str) -> None:
        a, b = self.a, self.b
        if corner == "equal":
            self.on_done(PairAnswer(a, b, self.context, "equal"))
            self.head.config(text=f"Пара «{a}» — «{b}»: A и B равноценны, веса равны")
            return
        ca, cb = self.ca, self.cb
        if corner == "a":
            sc = ca
            fixed = f"{a} = {self._v(ca, ca.worst)}, {b} = {self._v(cb, cb.best)}"
            var_tpl = lambda x: f"{a} = {self._v(ca, x)}, {b} = {self._v(cb, cb.worst)}"
            what = f"При каком значении «{a}» вариант ({a} = ?, {b} = {self._v(cb, cb.worst)}) " \
                   f"равноценен варианту B ({fixed})?"
        else:
            sc = cb
            fixed = f"{a} = {self._v(ca, ca.best)}, {b} = {self._v(cb, cb.worst)}"
            var_tpl = lambda x: f"{a} = {self._v(ca, ca.worst)}, {b} = {self._v(cb, x)}"
            what = f"При каком значении «{b}» вариант ({a} = {self._v(ca, ca.worst)}, {b} = ?) " \
                   f"равноценен варианту A ({fixed})?"
        self.head.config(text=f"Пара «{a}» — «{b}». Шаг 2: точка безразличия "
                              f"(лучше вариант {'A' if corner == 'a' else 'B'})")
        self._hide_corners()
        self._redraw(corner, None)

        def validate(v):
            if not sc.is_between(v, sc.worst, sc.best):
                raise MautError(f"Значение должно лежать строго между {self._v(sc, sc.worst)} и {self._v(sc, sc.best)}")

        spec = {
            "title": what,
            "context": "",
            "worse": sc.worst, "better": sc.best, "tol": self.p.bisection_tol * sc.span,
            "quantum": quantum(sc.span),
            "fmt": lambda x: self._v(sc, x),
            "prompt": what,
            "validate": validate,
            "option_x": var_tpl,
            "option_ref": fixed,
            "draw": lambda cv, x: self._redraw(corner, x),
        }

        def done(recs):
            self.on_done(PairAnswer(a, b, self.context, corner, recs[-1]))

        self.q.pack(anchor="w", fill="x", pady=(6, 0))
        self.q.set_spec(spec, done)
