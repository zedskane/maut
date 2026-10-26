"""Опрос ЛПР: прямой ввод и диалог «выше/ниже» делением отрезка пополам.

Все шаги метода сводятся к одному виду вопроса: найти значение x на шкале
(критерия или вероятности), при котором вариант с x равноценен для ЛПР
фиксированному варианту. Например:

* эквивалент определённости: «гарантированно x» против лотереи;
* точка безразличия для весов: (x, худшее по Cj) против (худшее, лучшее по Cj);
* вероятность p для мультипликативной модели: лотерея с p против
  гарантированного варианта.

У шкалы есть «худший» и «лучший» конец: чем ближе x к лучшему концу, тем
привлекательнее вариант с x. Поэтому один и тот же поиск подходит для всех
вопросов, а тексты вопросов формирует интерфейс.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import MautError

# Ответы в диалоге
PREFER_X = "x"        # вариант с текущим x лучше фиксированного
PREFER_REF = "ref"    # фиксированный вариант лучше
EQUAL = "equal"       # равноценны

ANSWERS = (PREFER_X, PREFER_REF, EQUAL)


@dataclass
class Record:
    """Результат одного опроса.

    mode — «direct» (ЛПР ввёл число сам) или «bisection» (диалог);
    questions — сколько вопросов задано; seconds — сколько времени занял
    опрос (если интерфейс его замерял); history — вопросы диалога в виде
    [x, ответ].
    """

    mode: str
    value: float
    questions: int = 1
    seconds: float | None = None
    history: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {"mode": self.mode, "value": self.value, "questions": self.questions}
        if self.seconds is not None:
            d["seconds"] = round(self.seconds, 2)
        if self.history:
            d["history"] = [[x, a] for x, a in self.history]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Record":
        return Record(
            d["mode"], float(d["value"]), int(d.get("questions", 1)),
            d.get("seconds"), [(float(x), a) for x, a in d.get("history", [])],
        )


def direct(value: float, seconds: float | None = None) -> Record:
    return Record("direct", float(value), 1, seconds)


class BisectionSession:
    """Поиск точки безразличия делением отрезка пополам.

    Отрезок [worse, better] — шкала, на которой ищется x. ЛПР каждый раз
    сравнивает вариант с x = середина текущего интервала и фиксированный
    вариант. Если вариант с x лучше, точка безразличия лежит ближе к худшему
    концу, и интервал сужается к нему; если хуже — к лучшему. Поиск
    останавливается, когда ширина интервала не больше tol (в единицах шкалы),
    ЛПР ответил «равноценно» или задано max_questions вопросов.
    """

    def __init__(self, worse: float, better: float, tol: float, max_questions: int = 30,
                 quantum: float = 0.0):
        if worse == better:
            raise MautError("Концы шкалы для поиска совпадают")
        if not tol > 0:
            raise MautError("Точность поиска должна быть больше 0")
        self.worse = float(worse)
        self.better = float(better)
        self.tol = float(tol)
        self.max_questions = int(max_questions)
        # Значение в вопросе округляется до quantum, чтобы ЛПР видел ровно то
        # число, с которым дальше работает поиск («162 млн», а не «162,5 млн»).
        self.quantum = float(quantum)
        self.lo = 0.0  # доля пути от худшего конца
        self.hi = 1.0
        self.equal_t: float | None = None
        self.history: list[tuple[float, str]] = []
        self._stack: list[tuple[float, float, float | None]] = []

    def _x(self, t: float) -> float:
        return self.worse + t * (self.better - self.worse)

    def _t(self, x: float) -> float:
        return (x - self.worse) / (self.better - self.worse)

    def current(self) -> float:
        """Значение x, о котором сейчас спрашивают ЛПР."""
        x = self._x((self.lo + self.hi) / 2)
        if self.quantum > 0:
            xq = round(x / self.quantum) * self.quantum
            if self.lo < self._t(xq) < self.hi:
                return xq
        return x

    @property
    def width(self) -> float:
        return (self.hi - self.lo) * abs(self.better - self.worse)

    @property
    def done(self) -> bool:
        if self.equal_t is not None:
            return True
        if len(self.history) >= self.max_questions:
            return True
        return bool(self.history) and self.width <= self.tol

    def answer(self, ans: str) -> None:
        if ans not in ANSWERS:
            raise MautError(f"Неизвестный ответ: {ans}")
        if self.done:
            raise MautError("Поиск уже завершён")
        x = self.current()
        t = self._t(x)
        self._stack.append((self.lo, self.hi, self.equal_t))
        self.history.append((x, ans))
        if ans == PREFER_X:
            self.hi = t
        elif ans == PREFER_REF:
            self.lo = t
        else:
            self.equal_t = t

    def undo(self) -> None:
        """Отменить последний ответ (ЛПР передумал)."""
        if not self.history:
            return
        self.lo, self.hi, self.equal_t = self._stack.pop()
        self.history.pop()

    @property
    def result(self) -> float:
        if self.equal_t is not None:
            return self._x(self.equal_t)
        return self._x((self.lo + self.hi) / 2)

    def record(self, seconds: float | None = None) -> Record:
        if not self.done:
            raise MautError("Поиск ещё не завершён")
        return Record("bisection", self.result, len(self.history), seconds, list(self.history))


def run_bisection(worse: float, better: float, tol: float, oracle, max_questions: int = 30,
                  quantum: float = 0.0) -> Record:
    """Провести диалог целиком; oracle(x) возвращает ответ ЛПР на вопрос о x.

    Используется в тестах, экспериментах и консольном режиме.
    """
    s = BisectionSession(worse, better, tol, max_questions, quantum)
    while not s.done:
        s.answer(oracle(s.current()))
    return s.record()
