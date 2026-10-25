#!/usr/bin/env python3
"""Question 5 -- Campagne de mesures des solveurs DPLL_H (et références).

    python benchmark.py [--timeout 30] [--jobs 8] [--out results/bench.csv]

Chaque couple (instance, solveur[, graine]) est exécuté dans un processus
fils ; le temps mesuré est le temps CPU du processus (time.process_time),
insensible à la charge des autres processus -- sauf sous Windows, où il est
remplacé par perf_counter (cf. ``solver.dpll.clock``) : utiliser alors au
plus un processus par cœur physique (--jobs). Les solveurs aléatoires
(algorithme 2, H0) sont exécutés avec 3 graines.
"""
import argparse
import csv
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from solver.heuristics import ALL_CODES
from solver.runner import run_one

# famille -> (motif glob, nombre d'instances, catégorie)
SETS = [
    ("uf20", "data/cnf/satlib/uf20-91/*.cnf", 10, "3-SAT"),
    ("uf50", "data/cnf/satlib/uf50-218/*.cnf", 10, "3-SAT"),
    ("uuf50", "data/cnf/satlib/uuf50-218/*.cnf", 10, "3-SAT"),
    ("uf75", "data/cnf/satlib/uf75-325/*.cnf", 5, "3-SAT"),
    ("uuf75", "data/cnf/satlib/uuf75-325/*.cnf", 5, "3-SAT"),
    ("rand3", "data/cnf/gen/rand3/*.cnf", 60, "3-SAT"),
    ("aim", "data/cnf/satlib/aim/aim-50-*.cnf", 12, "structuré"),
    ("dubois", "data/cnf/satlib/dubois/dubois2[0-3].cnf", 4, "structuré"),
    ("php", "data/cnf/gen/php/*.cnf", 5, "structuré"),
    ("flat50", "data/cnf/satlib/flat50-115/*.cnf", 5, "structuré"),
    ("meow_sat", "data/cnf/gen/meow_sat/*.cnf", 32, "Meowdoku"),
    ("meow_nored", "data/cnf/gen/meow_nored/*.cnf", 32, "Meowdoku"),
    ("meow_rnd", "data/cnf/gen/meow_rnd/*.cnf", 30, "Meowdoku"),
]
SEEDED = {"alg2", "dpllh:H0"}


def instances():
    out = []
    for fam, pat, k, cat in SETS:
        files = sorted(glob.glob(pat))[:k]
        out += [(fam, cat, f) for f in files]
    return out


def _task(t):
    fam, cat, path, solver, timeout, seed = t
    r = run_one(path, solver, timeout, seed)
    r["family"], r["category"] = fam, cat
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default="results/bench.csv")
    ap.add_argument("--solvers", nargs="*")
    a = ap.parse_args()
    solvers = a.solvers or (["alg2", "cdcl"] + [f"dpllh:{h}" for h in ALL_CODES])
    tasks = []
    for fam, cat, f in instances():
        for s in solvers:
            for seed in ((0, 1, 2) if s in SEEDED else (0,)):
                tasks.append((fam, cat, f, s, a.timeout, seed))
    # les tâches longues (grosses instances) d'abord pour équilibrer la charge
    tasks.sort(key=lambda t: -os.path.getsize(t[2]))
    print(f"{len(tasks)} exécutions", file=sys.stderr)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    rows = []
    with ProcessPoolExecutor(a.jobs) as ex:
        for i, r in enumerate(ex.map(_task, tasks, chunksize=1)):
            rows.append(r)
            if i % 200 == 0:
                print(f"  {i}/{len(tasks)}", file=sys.stderr, flush=True)
    keys = sorted({k for r in rows for k in r})
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    wrong = [r for r in rows if r["correct"] is False]
    print(f"terminé : {len(rows)} lignes, {len(wrong)} réponses incorrectes", file=sys.stderr)


if __name__ == "__main__":
    main()
