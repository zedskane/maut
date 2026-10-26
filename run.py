"""Расчёт по сохранённому проекту без окна.

python run.py examples/airport.json
python run.py examples/airport.json --model multiplicative --csv result.csv
"""

from __future__ import annotations

import argparse
import csv
import sys

from maut import MautError, Project
from maut.model import fmt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Метод MAUT: расчёт по файлу проекта")
    ap.add_argument("project", help="файл проекта (.json), сохранённый из окна")
    ap.add_argument("--model", choices=["additive", "multiplicative"], help="модель (по умолчанию из файла)")
    ap.add_argument("--csv", help="записать полезности альтернатив в CSV")
    args = ap.parse_args(argv)

    try:
        p = Project.load(args.project)
    except (OSError, MautError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1

    print(f"Проект: {p.title}\n")
    print("Функции полезности (значение → U):")
    for c in p.criteria:
        pts = sorted(p.known_points(c.name).items())
        line = ", ".join(f"{fmt(x, c.span)} → {fmt(u, 1)}" for u, x in pts)
        status = "" if p.curve_complete(c.name) else "  [построена не полностью]"
        print(f"  {c.name} ({c.unit}): {line}{status}")

    print("\nНезависимость по полезности (CE при наилучших / наихудших прочих):")
    for c in p.criteria:
        for r in p.ui_rows(c.name):
            if r["ce_best"] is None or r["ce_worst"] is None:
                print(f"  {c.name}, U = {fmt(r['u'], 1)}: не проверено")
                continue
            print(f"  {c.name}, U = {fmt(r['u'], 1)}: {fmt(r['ce_best'], c.span)} / "
                  f"{fmt(r['ce_worst'], c.span)}, разница {r['diff'] * 100:.1f} % — "
                  f"{'выполнено' if r['ok'] else 'НАРУШЕНО'}")

    print("\nНезависимость по предпочтению:")
    pairs = p.pi_pairs()
    if not pairs:
        print("  критериев меньше трёх — проверка не нужна")
    for a, b in pairs:
        r = p.pi_row(a, b)
        if r["ok"] is None:
            print(f"  {a} — {b}: не проверено")
        else:
            d = f", разница {r['diff'] * 100:.1f} %" if r["diff"] is not None else ""
            print(f"  {a} — {b}: {'выполнено' if r['ok'] else 'НАРУШЕНО (' + r['why'] + ')'}{d}")

    try:
        res = p.evaluate(model=args.model)
    except MautError as e:
        print(f"\nРасчёт невозможен: {e}", file=sys.stderr)
        return 2

    print("\nВеса: " + ", ".join(f"{n} = {w:.3f}" for n, w in res["weights"].items()))
    if res["model"] == "multiplicative":
        print("ki: " + ", ".join(f"{n} = {k:.3f}" for n, k in res["ks"].items()) + f"; k = {res['k']:.4f}")
    print(f"\nМногокритериальная полезность ({'аддитивная' if res['model'] == 'additive' else 'мультипликативная'}"
          " модель):")
    rows = sorted(res["rows"], key=lambda r: r["rank"])
    for r in rows:
        us = ", ".join(f"U({n}) = {u:.3f}" for n, u in r["u"].items())
        print(f"  {r['rank']}. {r['name']}: U = {r['U']:.3f}   ({us})")
    for w in res["warnings"]:
        print("  ! " + w)

    comps = p.mode_comparisons()
    if comps:
        print("\nСравнение режимов опроса:")
        for c in comps:
            print(f"  {c['what']}: прямой {c['direct'].value:.3f}, диалог {c['bisection'].value:.3f} "
                  f"({c['bisection'].questions} вопр.), разница {c['diff'] * 100:.1f} %")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f, delimiter=";")
            wr.writerow(["Ранг", "Альтернатива"] + [f"U({n})" for n in p.names()] + ["U"])
            for r in rows:
                # десятичная запятая — чтобы русский Excel сразу читал числа
                nums = [r["u"][n] for n in p.names()] + [r["U"]]
                wr.writerow([r["rank"], r["name"]] + [f"{x:.4f}".replace(".", ",") for x in nums])
        print(f"\nЗаписано: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
