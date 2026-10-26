"""Собрать файлы примеров «Аэропорт» (пример из методички).

python examples/make_examples.py

airport_empty.json — только критерии и альтернативы, опрос проводится в окне.
airport.json — все шаги пройдены:
* «Стоимость» — ответы из методички прямым вводом: U(185) = 0,25,
  U(160) = 0,5, U(130) = 0,75 (в методичке 0,85 — ошибка, см. отчёт);
* «Время» — диалог с модельным ЛПР;
* «Шум» — оба режима (для вкладки сравнения);
* веса по точкам безразличия из методички: U(200 млн, 40 мин) = U(170 млн, 90 мин),
  для шума — точка со стоимостью 148 млн (U = 0,6), откуда w = 0,5; 0,2; 0,3.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from maut import Alternative, Criterion, Project  # noqa: E402
from maut.elicitation import direct  # noqa: E402
from maut.simulator import SimulatedDM, piecewise_shape  # noqa: E402
from maut.weights import PairAnswer  # noqa: E402

COST, TIME, NOISE = "Стоимость", "Время в пути", "Шум"


def base() -> Project:
    p = Project("Выбор площадки для аэропорта (пример из методички)", [
        Criterion(COST, "млн", 200, 100),
        Criterion(TIME, "мин", 90, 40),
        Criterion(NOISE, "тыс. чел.", 50, 5),
    ], levels=2)
    p.alternatives = [
        Alternative("Северная", {COST: 180, TIME: 45, NOISE: 30}),
        Alternative("Речная", {COST: 120, TIME: 80, NOISE: 20}),
        Alternative("Восточная", {COST: 150, TIME: 60, NOISE: 12}),
        Alternative("Западная", {COST: 110, TIME: 85, NOISE: 45}),
        Alternative("Южная", {COST: 190, TIME: 50, NOISE: 8}),
    ]
    return p


def filled() -> Project:
    p = base()
    # «Стоимость»: значения из методички
    p.set_ce(COST, 0.5, direct(160))
    p.set_ce(COST, 0.25, direct(185))
    p.set_ce(COST, 0.75, direct(130))

    # модельный ЛПР с кривыми через нужные точки
    def shape(c, xs):
        return piecewise_shape([0, c.t(xs[0]), c.t(xs[1]), c.t(xs[2]), 1], [0, 0.25, 0.5, 0.75, 1])

    names = p.names()
    shapes = {COST: shape(p.criterion(COST), (185, 160, 130)),
              TIME: shape(p.criterion(TIME), (80, 70, 57)),
              NOISE: shape(p.criterion(NOISE), (41, 30, 17))}
    dm = SimulatedDM(p, SimulatedDM.additive(names, shapes, {COST: 0.5, TIME: 0.2, NOISE: 0.3}))

    for row in p.lotteries(TIME):
        row = p.lotteries(TIME)[row["index"]]
        p.set_ce(TIME, row["u"], dm.ce_record(TIME, row["x_lo"], row["x_hi"], "best", "bisection"))
    # «Шум»: ЛПР сначала назвал число сам, затем прошёл диалог
    for row, guess in zip(p.lotteries(NOISE), (32, 42, 15)):
        row = p.lotteries(NOISE)[row["index"]]
        p.set_ce(NOISE, row["u"], direct(guess))
        p.set_ce(NOISE, row["u"], dm.ce_record(NOISE, row["x_lo"], row["x_hi"], "best", "bisection"))

    # независимость по полезности: прочие критерии на наихудших значениях
    p.set_ui(COST, 0.5, direct(162))
    p.set_ui(TIME, 0.5, direct(71))
    p.set_ui(NOISE, 0.5, direct(31))

    # опорный критерий и независимость по предпочтению (пары с опорным)
    p.set_ref(COST)
    p.set_pi(PairAnswer(COST, TIME, "best", "a", direct(170)))
    p.set_pi(PairAnswer(COST, TIME, "worst", "a", direct(168)))
    p.set_pi(PairAnswer(COST, NOISE, "best", "a", direct(150)))
    p.set_pi(PairAnswer(COST, NOISE, "worst", "a", direct(148)))

    # веса: точки безразличия из методички
    p.set_weight_answer(PairAnswer(COST, TIME, "worst", "a", direct(170)))
    p.set_weight_answer(PairAnswer(COST, NOISE, "worst", "a", direct(148)))
    # вероятность для мультипликативной модели (модель по умолчанию — аддитивная)
    p.set_p(direct(0.55))
    return p


if __name__ == "__main__":
    base().save(HERE / "airport_empty.json")
    p = filled()
    p.save(HERE / "airport.json")
    print("Веса:", {k: round(v, 3) for k, v in p.weights().items()})
    for r in sorted(p.evaluate()["rows"], key=lambda r: r["rank"]):
        print(r["rank"], r["name"], round(r["U"], 3))
