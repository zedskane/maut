import math

import pytest

from maut import (BisectionSession, Criterion, MautError, Project, UtilityFunction,
                  lottery_plan, solve_k)
from maut.elicitation import EQUAL, PREFER_REF, PREFER_X, direct, run_bisection
from maut.simulator import SimulatedDM, exp_shape
from maut.weights import PairAnswer, multiplicative


def airport() -> Project:
    return Project("Аэропорт", [
        Criterion("Стоимость", "млн", 200, 100),
        Criterion("Время", "мин", 90, 40),
        Criterion("Шум", "тыс. чел.", 50, 5),
    ], levels=2)


# ---------------------------------------------------------------- лотереи

def test_plan_order_and_size():
    assert lottery_plan(1) == [(0, 1, 0.5)]
    assert lottery_plan(2) == [(0, 1, 0.5), (0, 0.5, 0.25), (0.5, 1, 0.75)]
    assert len(lottery_plan(3)) == 7


def test_curve_from_methodichka():
    """U(160) = 0,5; правая лотерея 160/100 даёт полезность 0,75 (в методичке 0,85)."""
    p = airport()
    p.set_ce("Стоимость", 0.5, direct(160))
    row = p.lotteries("Стоимость")[2]
    assert (row["x_lo"], row["x_hi"]) == (160, 100)
    p.set_ce("Стоимость", 0.75, direct(130))
    p.set_ce("Стоимость", 0.25, direct(185))
    u = p.utility("Стоимость")
    assert u(160) == pytest.approx(0.5)
    assert u(130) == pytest.approx(0.75)
    assert u(170) == pytest.approx(0.4)        # как в примере с весами
    assert u(250) == 0 and u(50) == 1          # за границами прижимается


def test_ce_must_be_inside_lottery():
    p = airport()
    with pytest.raises(MautError):
        p.set_ce("Стоимость", 0.5, direct(210))
    with pytest.raises(MautError):
        p.set_ce("Стоимость", 0.25, direct(180))  # родительская ещё не проведена


def test_changing_parent_resets_children():
    p = airport()
    p.set_ce("Стоимость", 0.5, direct(160))
    p.set_ce("Стоимость", 0.25, direct(185))
    p.set_ce("Стоимость", 0.75, direct(130))
    cleared = p.set_ce("Стоимость", 0.5, direct(150))
    assert cleared == [0.25, 0.75]
    assert not p.curve_complete("Стоимость")


def test_non_monotone_points_rejected():
    c = Criterion("x", "", 0, 10)
    with pytest.raises(MautError):
        UtilityFunction(c, [(0, 0), (6, 0.25), (4, 0.5), (10, 1)])


# ---------------------------------------------------------------- диалог

@pytest.mark.parametrize("target", [0.0, 3.3, 17.77, 42.0, 99.9])
def test_bisection_finds_point_within_tol(target):
    rec = run_bisection(0, 100, 1.0, lambda x: PREFER_X if x > target else PREFER_REF)
    assert abs(rec.value - target) <= 1.0
    assert rec.questions == 7  # 100 / 2^7 < 1


def test_bisection_reversed_scale():
    """Шкала, где лучшее меньше худшего (стоимость)."""
    rec = run_bisection(200, 100, 1.0, lambda x: PREFER_X if x < 160 else PREFER_REF)
    assert abs(rec.value - 160) <= 1.0


def test_bisection_equal_and_undo():
    s = BisectionSession(0, 100, 1.0)
    s.answer(PREFER_X)        # 50 лучше → ищем ниже
    assert s.current() == 25
    s.undo()
    assert s.current() == 50
    s.answer(EQUAL)
    assert s.done and s.result == 50 and s.record().questions == 1


# ---------------------------------------------------------------- веса и k

def test_weights_from_methodichka():
    """w2 = 0,4·w1 и w3 = 0,6·w1 → веса 0,5; 0,2; 0,3."""
    p = airport()
    for name, pts in {"Стоимость": (185, 160, 130), "Время": (80, 70, 55), "Шум": (40, 30, 15)}.items():
        p.set_ce(name, 0.5, direct(pts[1]))
        p.set_ce(name, 0.25, direct(pts[0]))
        p.set_ce(name, 0.75, direct(pts[2]))
    p.set_ref("Стоимость")
    p.set_weight_answer(PairAnswer("Стоимость", "Время", "worst", "a", direct(170)))
    u = p.utility("Стоимость")
    x150 = u.inverse(0.6)
    p.set_weight_answer(PairAnswer("Стоимость", "Шум", "worst", "a", direct(x150)))
    w = p.weights()
    assert w["Стоимость"] == pytest.approx(0.5)
    assert w["Время"] == pytest.approx(0.2)
    assert w["Шум"] == pytest.approx(0.3)


def test_weight_when_other_more_important():
    p = Project("", [Criterion("A", "", 0, 1), Criterion("B", "", 0, 1)], levels=1)
    p.set_ce("A", 0.5, direct(0.5))
    p.set_ce("B", 0.5, direct(0.5))
    p.set_ref("A")
    # B важнее: (A худшее, y=0,5) ~ (A лучшее, B худшее) → wA = wB·0,5
    p.set_weight_answer(PairAnswer("A", "B", "worst", "b", direct(0.5)))
    w = p.weights()
    assert w["B"] == pytest.approx(2 * w["A"])


@pytest.mark.parametrize("ks", [[0.3, 0.2, 0.1], [0.6, 0.5, 0.4], [0.45, 0.35], [0.9, 0.05]])
def test_solve_k_satisfies_equation(ks):
    k = solve_k(ks)
    assert k != 0
    assert 1 + k == pytest.approx(math.prod(1 + k * ki for ki in ks), abs=1e-9)
    assert (k > 0) == (sum(ks) < 1)
    assert multiplicative(ks, k, [1] * len(ks)) == pytest.approx(1)
    assert multiplicative(ks, k, [0] * len(ks)) == pytest.approx(0)


def test_solve_k_additive_case():
    assert solve_k([0.5, 0.3, 0.2]) == 0.0


# ---------------------------------------------------------------- модельный ЛПР

def test_exact_dm_recovers_weights_and_curves():
    p = airport()
    p.levels = 3
    p.bisection_tol = 0.001
    names = p.names()
    a = {"Стоимость": 2.0, "Время": -1.0, "Шум": 0.5}
    w = {"Стоимость": 0.5, "Время": 0.2, "Шум": 0.3}
    shapes = {n: exp_shape(a[n]) for n in names}
    dm = SimulatedDM(p, SimulatedDM.additive(names, shapes, w))
    dm.fill("bisection")
    for n in names:
        u = p.utility(n)
        c = p.criterion(n)
        err = max(abs(u(c.x(t / 100)) - shapes[n](t / 100)) for t in range(101))
        assert err < 0.03
        assert p.ui_status(n) is True
    assert p.pi_status() is True
    for n, wn in p.weights().items():
        assert wn == pytest.approx(w[n], abs=0.02)


def test_dm_with_dependence_is_detected():
    p = airport()
    names = p.names()
    a = {n: 0.0 for n in names}
    w = {"Стоимость": 0.5, "Время": 0.2, "Шум": 0.3}
    dm = SimulatedDM(p, SimulatedDM.utility_dependent(names, a, w, "Стоимость", 3.0))
    dm.fill("bisection")
    assert p.ui_status("Стоимость") is False
    assert p.ui_status("Время") is True


def test_preference_dependence_is_detected():
    p = airport()
    p.pi_full = True
    names = p.names()
    a = {n: 0.0 for n in names}
    w = {"Стоимость": 0.4, "Время": 0.3, "Шум": 0.3}
    V = SimulatedDM.preference_dependent(names, a, w, ("Стоимость", "Время"), "Шум", 0.25)
    SimulatedDM(p, V).fill("bisection")
    assert p.pi_row("Стоимость", "Время")["ok"] is False
    assert p.pi_status() is False


def test_multiplicative_exact_dm():
    """ЛПР с мультипликативной V: модель восстанавливает V в любой точке."""
    p = airport()
    p.levels = 3
    p.bisection_tol = 0.0005
    names = p.names()
    ks_true = {"Стоимость": 0.6, "Время": 0.3, "Шум": 0.4}
    k_true = solve_k(list(ks_true.values()))
    shapes = {n: exp_shape(1.0) for n in names}

    def V(t):
        return multiplicative([ks_true[n] for n in names], k_true, [shapes[n](t[n]) for n in names])

    SimulatedDM(p, V).fill("bisection", multiplicative=True)
    ks = p.scaling()
    for n in names:
        assert ks[n] == pytest.approx(ks_true[n], abs=0.01)
    assert p.k() == pytest.approx(k_true, abs=0.05)


# ---------------------------------------------------------------- файлы и правка

def test_json_roundtrip(tmp_path):
    p = airport()
    names = p.names()
    dm = SimulatedDM(p, SimulatedDM.additive(names, {n: exp_shape(1) for n in names},
                                             {n: 1 for n in names}), sigma_direct=0.05, seed=1)
    dm.fill("direct", multiplicative=False)
    from maut import Alternative
    p.alternatives = [Alternative("A", {"Стоимость": 150, "Время": 60, "Шум": 20})]
    f = tmp_path / "p.json"
    p.save(f)
    q = Project.load(f)
    assert q.to_dict() == p.to_dict()
    assert q.evaluate()["rows"][0]["U"] == pytest.approx(p.evaluate()["rows"][0]["U"])


def test_rename_keeps_answers_and_range_change_clears():
    p = airport()
    p.set_ce("Стоимость", 0.5, direct(160))
    p.update_criterion("Стоимость", Criterion("Цена", "млн", 200, 100))
    assert p.known_points("Цена")[0.5] == 160
    p.update_criterion("Цена", Criterion("Цена", "млн", 250, 100))
    assert 0.5 not in p.known_points("Цена")


def test_alternative_out_of_range_warns():
    p = Project("", [Criterion("A", "", 0, 10)], levels=1)
    p.set_ce("A", 0.5, direct(4))
    from maut import Alternative
    res = p.evaluate([Alternative("x", {"A": 12}), Alternative("y", {"A": 4})])
    assert res["rows"][0]["U"] == 1.0 and res["rows"][0]["rank"] == 1
    assert res["rows"][1]["U"] == pytest.approx(0.5)
    assert res["warnings"]


def test_bisection_quantum_shows_round_numbers():
    """Вопросы задаются в округлённых значениях, и поиск работает именно с ними."""
    asked = []

    def oracle(x):
        asked.append(x)
        return PREFER_X if x < 160 else PREFER_REF

    rec = run_bisection(200, 100, 1.0, oracle, quantum=1.0)
    assert all(abs(x - round(x)) < 1e-9 for x in asked)
    assert abs(rec.value - 160) <= 1.0
