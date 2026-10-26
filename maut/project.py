"""Состояние метода MAUT: критерии, ответы ЛПР, проверки, веса, альтернативы.

Ответы хранятся как списки попыток (Record): действующей считается последняя.
Если на одну лотерею ответили и прямым вводом, и диалогом, обе попытки
остаются в файле и попадают в сравнение режимов.

Порядок шагов:
1. критерии с наихудшими и наилучшими значениями;
2. лотереи для однокритериальных функций полезности (прочие критерии на
   наилучших значениях);
3. проверка независимости по полезности: те же лотереи при наихудших
   значениях прочих критериев;
4. проверка независимости по предпочтению: точки безразличия на плоскостях
   пар критериев при наилучших и наихудших значениях прочих;
5. веса: точки безразличия опорного (самого важного) критерия с каждым
   другим, прочие критерии на наихудших значениях; для мультипликативной
   модели ещё вероятность p;
6. многокритериальная полезность альтернатив.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from .elicitation import Record
from .model import Alternative, Criterion, MautError, fmt
from .utility import UtilityFunction, lottery_plan, points_for_levels, ukey
from .weights import PairAnswer, multiplicative, normalize, solve_k

FORMAT_VERSION = 1
CONTEXTS = ("best", "worst")


class Project:
    def __init__(self, title: str = "", criteria: list[Criterion] | None = None, levels: int = 2):
        self.title = title
        self.criteria: list[Criterion] = list(criteria or [])
        self.levels = levels
        # параметры
        self.bisection_tol = 0.01   # точность диалога, доля диапазона шкалы
        self.ui_tol = 0.10          # допуск совпадения CE, доля диапазона критерия (см. опыт 3)
        self.pi_tol = 0.10          # допуск совпадения точек безразличия
        self.ui_full = False        # проверять все лотереи (иначе только первую)
        self.pi_full = False        # проверять все пары (иначе только пары с опорным)
        self.model = "additive"     # или «multiplicative»
        # ответы
        self.curves: dict[str, dict[str, list[Record]]] = {}
        self.ui: dict[str, dict[str, list[Record]]] = {}
        self.pi: dict[str, PairAnswer] = {}
        self.ref: str | None = None
        self.weight_answers: dict[str, PairAnswer] = {}
        self.p_ref: list[Record] = []
        self.alternatives: list[Alternative] = []

    # ------------------------------------------------------------------ критерии

    def names(self) -> list[str]:
        return [c.name for c in self.criteria]

    def criterion(self, name: str) -> Criterion:
        for c in self.criteria:
            if c.name == name:
                return c
        raise MautError(f"Нет критерия «{name}»")

    def validate_criteria(self) -> None:
        if not self.criteria:
            raise MautError("Не задано ни одного критерия")
        seen = set()
        for c in self.criteria:
            c.validate()
            if c.name in seen:
                raise MautError(f"Два критерия с названием «{c.name}»")
            seen.add(c.name)

    def add_criterion(self, c: Criterion) -> None:
        c.validate()
        if c.name in self.names():
            raise MautError(f"Критерий «{c.name}» уже есть")
        self.criteria.append(c)
        # новый критерий меняет контекст всех вопросов с «прочими критериями»
        self._clear_context_dependent()

    def remove_criterion(self, name: str) -> None:
        self.criterion(name)
        self.criteria = [c for c in self.criteria if c.name != name]
        self._forget(name)
        self._clear_context_dependent()
        for a in self.alternatives:
            a.values.pop(name, None)

    def update_criterion(self, old_name: str, new: Criterion) -> list[str]:
        """Изменить критерий. Возвращает список того, что пришлось сбросить."""
        new.validate()
        old = self.criterion(old_name)
        if new.name != old_name and new.name in self.names():
            raise MautError(f"Критерий «{new.name}» уже есть")
        cleared = []
        if (old.worst, old.best) != (new.worst, new.best):
            # ответы ЛПР давались для старого диапазона — они больше не верны
            self._forget(old_name)
            self._clear_context_dependent()
            cleared.append("ответы ЛПР, зависящие от диапазона")
        if new.name != old_name:
            self._rename(old_name, new.name)
        idx = self.criteria.index(old)
        self.criteria[idx] = new
        return cleared

    def _rename(self, old: str, new: str) -> None:
        for store in (self.curves, self.ui):
            if old in store:
                store[new] = store.pop(old)
        pi = {}
        for key, ans in self.pi.items():
            if ans.a == old:
                ans.a = new
            if ans.b == old:
                ans.b = new
            pi[self._pi_key(ans.a, ans.b, ans.context)] = ans
        self.pi = pi
        if self.ref == old:
            self.ref = new
        wa = {}
        for other, ans in self.weight_answers.items():
            if ans.a == old:
                ans.a = new
            if ans.b == old:
                ans.b = new
            wa[ans.b] = ans
        self.weight_answers = wa
        for a in self.alternatives:
            if old in a.values:
                a.values[new] = a.values.pop(old)

    def _forget(self, name: str) -> None:
        self.curves.pop(name, None)
        self.ui.pop(name, None)
        self.pi = {k: v for k, v in self.pi.items() if name not in (v.a, v.b)}
        if self.ref == name:
            self.ref = None
            self.weight_answers = {}
        self.weight_answers.pop(name, None)
        self.p_ref = []

    def _clear_context_dependent(self) -> None:
        """Сбросить ответы, в которых упоминались значения «прочих критериев»."""
        self.ui = {}
        self.pi = {}
        self.weight_answers = {}
        self.p_ref = []

    def others(self, name: str) -> list[Criterion]:
        return [c for c in self.criteria if c.name != name]

    # ------------------------------------------------------------- лотереи (шаг 2)

    def set_levels(self, levels: int) -> None:
        if levels == self.levels:
            return
        if levels < self.levels:
            # лишние лотереи глубоких уровней просто перестают учитываться
            keep = {ukey(m) for _, _, m in lottery_plan(levels)}
            for store in (self.curves, self.ui):
                for name in store:
                    store[name] = {k: v for k, v in store[name].items() if k in keep}
        self.levels = levels

    @property
    def n_points(self) -> int:
        return points_for_levels(self.levels)

    def plan(self) -> list[tuple[float, float, float]]:
        return lottery_plan(self.levels)

    def known_points(self, name: str) -> dict[float, float]:
        """Известные точки кривой: полезность → значение критерия."""
        c = self.criterion(name)
        pts = {0.0: c.worst, 1.0: c.best}
        for lo, hi, mid in self.plan():
            recs = self.curves.get(name, {}).get(ukey(mid))
            if recs:
                pts[mid] = recs[-1].value
        return pts

    def lottery_endpoints(self, name: str, lo: float, hi: float) -> tuple[float, float] | None:
        pts = self.known_points(name)
        if lo in pts and hi in pts:
            return pts[lo], pts[hi]
        return None

    def lotteries(self, name: str) -> list[dict]:
        """Лотереи критерия с состоянием: можно ли проводить, проведена ли."""
        rows = []
        for i, (lo, hi, mid) in enumerate(self.plan()):
            ends = self.lottery_endpoints(name, lo, hi)
            recs = self.curves.get(name, {}).get(ukey(mid), [])
            rows.append({
                "index": i, "u_lo": lo, "u_hi": hi, "u": mid,
                "x_lo": ends[0] if ends else None, "x_hi": ends[1] if ends else None,
                "available": ends is not None,
                "record": recs[-1] if recs else None,
                "attempts": list(recs),
            })
        return rows

    def set_ce(self, name: str, u: float, record: Record) -> list[float]:
        """Записать эквивалент определённости лотереи с полезностью u.

        Возвращает полезности точек, которые пришлось сбросить: они строились
        на прежнем значении этой точки.
        """
        lot = self._find_lottery(u)
        ends = self.lottery_endpoints(name, lot[0], lot[1])
        if ends is None:
            raise MautError("Сначала проведите лотереи, на которые опирается эта")
        c = self.criterion(name)
        if not c.is_between(record.value, *ends):
            raise MautError(
                f"Эквивалент определённости должен лежать строго между исходами лотереи: "
                f"{fmt(ends[0], c.span)} и {fmt(ends[1], c.span)} {c.unit}"
            )
        recs = self.curves.setdefault(name, {}).setdefault(ukey(u), [])
        changed = bool(recs) and recs[-1].value != record.value
        recs.append(record)
        cleared = []
        if changed:
            lo, hi = lot[0], lot[1]
            for k in list(self.curves[name]):
                uu = float(k)
                if lo < uu < hi and uu != u:
                    del self.curves[name][k]
                    cleared.append(uu)
            # у сброшенных лотерей сменились исходы — их проверки тоже не годятся
            for k in list(self.ui.get(name, {})):
                if float(k) in cleared:
                    del self.ui[name][k]
        return sorted(cleared)

    def _find_lottery(self, u: float) -> tuple[float, float, float]:
        for lot in self.plan():
            if abs(lot[2] - u) < 1e-12:
                return lot
        raise MautError(f"Нет лотереи с полезностью {u}")

    def curve_complete(self, name: str) -> bool:
        return len(self.known_points(name)) == self.n_points

    def utility(self, name: str, partial: bool = False) -> UtilityFunction:
        if not partial and not self.curve_complete(name):
            raise MautError(f"«{name}»: функция полезности построена не полностью")
        pts = self.known_points(name)
        return UtilityFunction(self.criterion(name), [(x, u) for u, x in pts.items()])

    def utilities(self) -> dict[str, UtilityFunction]:
        return {n: self.utility(n) for n in self.names()}

    # ------------------------------------------ независимость по полезности (шаг 3)

    def ui_lotteries(self, name: str) -> list[tuple[float, float, float]]:
        plan = self.plan()
        return plan if self.ui_full else plan[:1]

    def set_ui(self, name: str, u: float, record: Record) -> None:
        """CE лотереи при наихудших значениях прочих критериев."""
        lot = self._find_lottery(u)
        ends = self.lottery_endpoints(name, lot[0], lot[1])
        if ends is None or ukey(u) not in self.curves.get(name, {}):
            raise MautError("Сначала проведите эту лотерею на шаге построения функции полезности")
        c = self.criterion(name)
        if not c.is_between(record.value, *ends):
            raise MautError(
                f"Эквивалент определённости должен лежать строго между "
                f"{fmt(ends[0], c.span)} и {fmt(ends[1], c.span)} {c.unit}"
            )
        self.ui.setdefault(name, {}).setdefault(ukey(u), []).append(record)

    def ui_rows(self, name: str) -> list[dict]:
        c = self.criterion(name)
        rows = []
        for lo, hi, mid in self.ui_lotteries(name):
            ends = self.lottery_endpoints(name, lo, hi)
            best = self.curves.get(name, {}).get(ukey(mid))
            worst = self.ui.get(name, {}).get(ukey(mid))
            row = {"u": mid, "u_lo": lo, "u_hi": hi,
                   "x_lo": ends[0] if ends else None, "x_hi": ends[1] if ends else None,
                   "available": bool(ends and best),
                   "ce_best": best[-1].value if best else None,
                   "ce_worst": worst[-1].value if worst else None,
                   "diff": None, "ok": None}
            if best and worst:
                row["diff"] = abs(best[-1].value - worst[-1].value) / c.span
                row["ok"] = row["diff"] <= self.ui_tol + 1e-12
            rows.append(row)
        return rows

    def ui_status(self, name: str) -> bool | None:
        """True — независим, False — нарушение, None — проверка не закончена."""
        rows = self.ui_rows(name)
        if any(r["ok"] is False for r in rows):
            return False
        if all(r["ok"] for r in rows):
            return True
        return None

    # ---------------------------------------- независимость по предпочтению (шаг 4)

    @staticmethod
    def _pi_key(a: str, b: str, ctx: str) -> str:
        return f"{a}|{b}|{ctx}"

    def pi_pairs(self) -> list[tuple[str, str]]:
        names = self.names()
        if len(names) < 3:
            return []  # нет «прочих» критериев — условие выполняется тривиально
        if self.pi_full or self.ref is None:
            return list(combinations(names, 2))
        return [(self.ref, n) for n in names if n != self.ref]

    def set_pi(self, ans: PairAnswer) -> None:
        ans.validate()
        if ans.context not in CONTEXTS:
            raise MautError("Контекст проверки: «best» или «worst»")
        self._check_pair_record(ans)
        self.pi[self._pi_key(ans.a, ans.b, ans.context)] = ans

    def pi_answer(self, a: str, b: str, ctx: str) -> PairAnswer | None:
        return self.pi.get(self._pi_key(a, b, ctx))

    def pi_row(self, a: str, b: str) -> dict:
        best, worst = self.pi_answer(a, b, "best"), self.pi_answer(a, b, "worst")
        row = {"a": a, "b": b, "best": best, "worst": worst, "diff": None, "ok": None, "why": ""}
        if not (best and worst):
            return row
        if best.corner != worst.corner:
            row["ok"] = False
            row["why"] = "при разных значениях прочих критериев важнее разный критерий пары"
        elif best.corner == "equal":
            row["ok"] = True
        else:
            c = self.criterion(best.scale)
            row["diff"] = abs(best.record.value - worst.record.value) / c.span
            row["ok"] = row["diff"] <= self.pi_tol + 1e-12
            if not row["ok"]:
                row["why"] = "точки безразличия различаются больше допуска"
        return row

    def pi_status(self) -> bool | None:
        pairs = self.pi_pairs()
        if not pairs:
            return True
        rows = [self.pi_row(a, b) for a, b in pairs]
        if any(r["ok"] is False for r in rows):
            return False
        if all(r["ok"] for r in rows):
            return True
        return None

    # ------------------------------------------------------------- веса (шаг 5)

    def set_ref(self, name: str | None) -> None:
        if name is not None:
            self.criterion(name)
        if name != self.ref:
            self.ref = name
            self.weight_answers = {}
            self.p_ref = []

    def set_weight_answer(self, ans: PairAnswer) -> None:
        if self.ref is None:
            raise MautError("Сначала выберите опорный (самый важный) критерий")
        if ans.a != self.ref or ans.b == self.ref:
            raise MautError("В паре для весов первым должен быть опорный критерий")
        ans.context = "worst"
        ans.validate()
        self._check_pair_record(ans)
        self.weight_answers[ans.b] = ans

    def _check_pair_record(self, ans: PairAnswer) -> None:
        if ans.record is None:
            return
        c = self.criterion(ans.scale)
        if not c.is_between(ans.record.value, c.worst, c.best):
            raise MautError(
                f"Точка безразличия должна лежать строго между наихудшим и наилучшим "
                f"значением «{c.name}»: {fmt(c.worst, c.span)} и {fmt(c.best, c.span)} {c.unit}"
            )

    def weight_ratios(self) -> dict[str, float]:
        """Отношения wj / w_ref для всех критериев, кроме опорного."""
        if self.ref is None:
            raise MautError("Не выбран опорный критерий")
        missing = [n for n in self.names() if n != self.ref and n not in self.weight_answers]
        if missing:
            raise MautError("Не найдены точки безразличия для: " + ", ".join(missing))
        ratios = {}
        for n in self.names():
            if n == self.ref:
                continue
            ans = self.weight_answers[n]
            ratios[n] = ans.ratio({ans.scale: self.utility(ans.scale)} if ans.scale else {})
        return ratios

    def weights(self) -> dict[str, float]:
        """Нормированные веса аддитивной модели (сумма 1)."""
        if len(self.criteria) == 1:
            return {self.criteria[0].name: 1.0}
        return normalize(self.weight_ratios(), self.ref)

    def set_p(self, record: Record) -> None:
        if not 0 < record.value < 1:
            raise MautError("Вероятность p должна быть в интервале (0, 1)")
        self.p_ref.append(record)

    def scaling(self) -> dict[str, float]:
        """Коэффициенты ki мультипликативной модели: k_ref = p, kj = p·(wj/w_ref)."""
        if not self.p_ref:
            raise MautError("Для мультипликативной модели нужна вероятность p")
        p = self.p_ref[-1].value
        ks = {self.ref: p}
        for n, r in self.weight_ratios().items():
            ks[n] = p * r
        bad = [n for n, k in ks.items() if not k < 1]
        if bad:
            raise MautError(
                "Коэффициенты ki должны быть меньше 1, а у критериев " + ", ".join(bad) +
                " получилось больше. Уменьшите p или проверьте точки безразличия."
            )
        return ks

    def k(self) -> float:
        return solve_k(list(self.scaling().values()))

    # ------------------------------------------------------ альтернативы (шаг 6)

    def check_alternative(self, alt: Alternative) -> list[str]:
        """Предупреждения по альтернативе (значения вне диапазона)."""
        warns = []
        for c in self.criteria:
            if c.name not in alt.values:
                raise MautError(f"«{alt.name}»: не задано значение по критерию «{c.name}»")
            v = alt.values[c.name]
            lo, hi = sorted((c.worst, c.best))
            if not lo <= v <= hi:
                warns.append(
                    f"«{alt.name}»: {c.name} = {fmt(v, c.span)} вне диапазона "
                    f"[{fmt(lo, c.span)}; {fmt(hi, c.span)}], полезность взята на границе"
                )
        return warns

    def evaluate(self, alternatives: list[Alternative] | None = None, model: str | None = None) -> dict:
        """Многокритериальная полезность и ранги альтернатив.

        Возвращает словарь: rows (по альтернативам: name, u — словарь Ui,
        contrib — вклад критериев для аддитивной модели, U, rank),
        weights, ks и k (для мультипликативной), warnings.
        """
        alts = self.alternatives if alternatives is None else alternatives
        model = model or self.model
        if not alts:
            raise MautError("Не задано ни одной альтернативы")
        utils = self.utilities()
        w = self.weights()
        res = {"model": model, "weights": w, "warnings": []}
        if model == "multiplicative":
            ks = self.scaling()
            k = solve_k(list(ks.values()))
            res.update(ks=ks, k=k)
        rows = []
        for alt in alts:
            res["warnings"] += self.check_alternative(alt)
            u = {n: utils[n](alt.values[n]) for n in self.names()}
            if model == "multiplicative":
                names = self.names()
                total = multiplicative([ks[n] for n in names], k, [u[n] for n in names])
                contrib = None
            else:
                contrib = {n: w[n] * u[n] for n in self.names()}
                total = sum(contrib.values())
            rows.append({"name": alt.name, "u": u, "contrib": contrib, "U": total})
        order = sorted(range(len(rows)), key=lambda i: -rows[i]["U"])
        for rank, i in enumerate(order, 1):
            rows[i]["rank"] = rank
        res["rows"] = rows
        return res

    # --------------------------------------------------------------- сводка шагов

    def progress(self) -> list[tuple[str, str]]:
        """Состояние шагов для строки статуса: (шаг, состояние)."""
        out = []
        n = len(self.criteria)
        out.append(("Критерии", f"{n}"))
        done = sum(self.curve_complete(c) for c in self.names())
        out.append(("Функции полезности", f"{done} из {n}"))
        st = [self.ui_status(c) for c in self.names()]
        out.append(("Независимость по полезности", _status_text(st)))
        out.append(("Независимость по предпочтению", _status_text([self.pi_status()])))
        try:
            self.weights()
            wtxt = "найдены"
        except MautError:
            wtxt = "не найдены"
        out.append(("Веса", wtxt))
        out.append(("Альтернативы", f"{len(self.alternatives)}"))
        return out

    def mode_comparisons(self) -> list[dict]:
        """Опросы, проведённые обоими режимами (для сравнения)."""
        rows = []

        def add(label: str, recs: list[Record], span: float):
            last = {}
            for r in recs:
                last[r.mode] = r
            if "direct" in last and "bisection" in last:
                d, b = last["direct"], last["bisection"]
                rows.append({"what": label, "direct": d, "bisection": b,
                             "diff": abs(d.value - b.value) / span})

        for c in self.criteria:
            for lo, hi, mid in self.plan():
                recs = self.curves.get(c.name, {}).get(ukey(mid), [])
                add(f"{c.name}: лотерея U = {fmt(mid, 1)}", recs, c.span)
                recs = self.ui.get(c.name, {}).get(ukey(mid), [])
                add(f"{c.name}: проверка, U = {fmt(mid, 1)}", recs, c.span)
        if self.p_ref:
            add("вероятность p", self.p_ref, 1.0)
        return rows

    # -------------------------------------------------------------------- файлы

    def to_dict(self) -> dict:
        def recs(store):
            return {n: {k: [r.to_dict() for r in v] for k, v in d.items()} for n, d in store.items()}

        return {
            "format": FORMAT_VERSION,
            "title": self.title,
            "criteria": [c.to_dict() for c in self.criteria],
            "settings": {
                "points": self.n_points, "bisection_tol": self.bisection_tol,
                "ui_tol": self.ui_tol, "pi_tol": self.pi_tol,
                "ui_full": self.ui_full, "pi_full": self.pi_full, "model": self.model,
            },
            "curves": recs(self.curves),
            "utility_independence": recs(self.ui),
            "preference_independence": [a.to_dict() for a in self.pi.values()],
            "reference": self.ref,
            "weights": [a.to_dict() for a in self.weight_answers.values()],
            "p": [r.to_dict() for r in self.p_ref],
            "alternatives": [a.to_dict() for a in self.alternatives],
        }

    @staticmethod
    def from_dict(d: dict) -> "Project":
        from .utility import levels_for_points

        if d.get("format", 1) > FORMAT_VERSION:
            raise MautError("Файл создан более новой версией программы")
        s = d.get("settings", {})
        p = Project(d.get("title", ""), [Criterion.from_dict(c) for c in d.get("criteria", [])],
                    levels_for_points(int(s.get("points", 5))))
        p.validate_criteria()
        p.bisection_tol = float(s.get("bisection_tol", p.bisection_tol))
        p.ui_tol = float(s.get("ui_tol", p.ui_tol))
        p.pi_tol = float(s.get("pi_tol", p.pi_tol))
        p.ui_full = bool(s.get("ui_full", False))
        p.pi_full = bool(s.get("pi_full", False))
        p.model = s.get("model", "additive")

        def recs(raw):
            return {n: {k: [Record.from_dict(r) for r in v] for k, v in dd.items()} for n, dd in raw.items()}

        p.curves = recs(d.get("curves", {}))
        p.ui = recs(d.get("utility_independence", {}))
        for a in d.get("preference_independence", []):
            ans = PairAnswer.from_dict(a)
            p.pi[p._pi_key(ans.a, ans.b, ans.context)] = ans
        p.ref = d.get("reference")
        for a in d.get("weights", []):
            ans = PairAnswer.from_dict(a)
            p.weight_answers[ans.b] = ans
        p.p_ref = [Record.from_dict(r) for r in d.get("p", [])]
        p.alternatives = [Alternative.from_dict(a) for a in d.get("alternatives", [])]
        return p

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> "Project":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise MautError(f"Файл не похож на проект MAUT: {e}") from e
        return Project.from_dict(data)


def _status_text(sts: list) -> str:
    if any(s is False for s in sts):
        return "нарушена"
    if sts and all(s is True for s in sts):
        return "выполнена"
    return "не проверена"
