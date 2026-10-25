#!/usr/bin/env python3
"""Question 4 -- Choix de la case dans la clause positive de H9 (MRV).

H9 branche sur la plus petite clause entièrement positive et pose un chat
dans l'une de ses cases. Trois variantes du choix de la case :
  least  la moins contraignante (son littéral négatif apparaît le moins dans
         les clauses binaires) -- variante retenue pour H9 ;
  index  le plus petit indice ;
  most   la plus contraignante.
Instances : grilles plantées 16 × 16 à 24 × 24 et grilles à régions
aléatoires 12 × 12 à 16 × 16 (les plus difficiles pour DPLL, cf. Q5).

    python experiments/h9_variants.py [--timeout 30] [--jobs 6]
Résultats : results/benchmark/h9_variants.csv + résumé sur la sortie standard.
"""
import argparse
import csv
import glob
import os
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du dépôt
sys.path.insert(0, ROOT)

from solver.cnf import check_model, parse_dimacs  # noqa: E402
from solver.dpll import Timeout  # noqa: E402
from solver.dpll_h import DPLLH  # noqa: E402
from solver.heuristics import MRV  # noqa: E402
from solver.runner import expected_status  # noqa: E402

PATTERNS = ["data/generated/cnf/meow_sat/meow_1[68]x*.cnf", "data/generated/cnf/meow_sat/meow_2[04]x*.cnf",
            "data/generated/cnf/meow_rnd/rnd_1[246]x*.cnf"]


def _task(t):
    path, choice, timeout = t
    cnf = parse_dimacs(path)
    d = DPLLH(MRV(choice), timeout)
    try:
        sat, model = d.solve(cnf.clauses, cnf.num_vars)
        status = "SAT" if sat else "UNSAT"
        ok = status == expected_status(path, cnf) and (not sat or check_model(cnf.clauses, model))
    except Timeout:
        status, ok = "TIMEOUT", None
    return {"instance": os.path.relpath(path, ROOT), "choice": choice, "status": status, "correct": ok,
            "cpu": d.stats.time_total, "decisions": d.stats.decisions}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--out", default="results/benchmark/h9_variants.csv")
    a = ap.parse_args()
    files = sorted(f for p in PATTERNS for f in glob.glob(os.path.join(ROOT, p)))
    tasks = [(f, c, a.timeout) for f in files for c in MRV.CHOICES]
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(_task, tasks, chunksize=1))
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(files)} instances, limite {a.timeout:g} s (PAR-2 : délai dépassé compté 2 × limite)")
    for c in MRV.CHOICES:
        rs = [r for r in rows if r["choice"] == c]
        par2 = [r["cpu"] if r["status"] != "TIMEOUT" else 2 * a.timeout for r in rs]
        print(f"  {c:6s} résolues {sum(r['status'] != 'TIMEOUT' for r in rs):2d}/{len(rs)}  "
              f"PAR-2 moyen {statistics.mean(par2):5.1f} s  "
              f"décisions médianes {statistics.median(r['decisions'] for r in rs):7.0f}  "
              f"réponses fausses {sum(r['correct'] is False for r in rs)}")


if __name__ == "__main__":
    main()
