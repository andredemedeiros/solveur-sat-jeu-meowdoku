#!/usr/bin/env python3
"""Questions 2.3 et 4 -- Validation des solveurs.

Pour chaque instance et chaque solveur (algorithme 1, algorithme 2, DPLL_H
avec chaque heuristique, CDCL) : comparaison du statut avec le statut attendu
(expected.json des instances publiques, commentaire « status » calculé par
pycosat, ou nom SATLIB) et vérification de chaque modèle renvoyé.

    python experiments/validate.py [--timeout 20] [--jobs 8] [dossiers ...]
Résultats : results/validation/validation.csv + résumé sur la sortie standard.
"""
import argparse
import csv
import glob
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du dépôt
sys.path.insert(0, ROOT)

from solver.heuristics import ALL_CODES  # noqa: E402
from solver.runner import run_one  # noqa: E402

DEFAULT_SETS = {  # dossier -> nombre max d'instances
    "data/satlib/uf20-91": 25, "data/satlib/uf50-218": 15, "data/satlib/uuf50-218": 15,
    "data/satlib/uf75-325": 5, "data/satlib/uuf75-325": 5, "data/satlib/aim": 12,
    "data/satlib/dubois": 4, "data/satlib/pigeon-hole": 2, "data/satlib/flat50-115": 3,
    "data/generated/cnf/rand3": 20, "data/generated/cnf/php": 4, "data/generated/cnf/meow_sat": 12,
    "data/generated/cnf/meow_rnd": 15, "data/examples/lampes.cnf": 1, "data/examples/grille1.cnf": 1,
    "data/public-instances/instances": 41,  # fichiers fournis par les enseignants (tous)
}


def pick(path, k, rng):
    if path.endswith(".cnf"):
        return [path]
    files = sorted(glob.glob(os.path.join(path, "*.cnf")))
    files.sort(key=lambda f: os.path.getsize(f))
    return files[:k] if len(files) <= k else sorted(rng.sample(files[: 3 * k], k))


def _task(args):
    return run_one(*args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sets", nargs="*")
    ap.add_argument("--timeout", type=float, default=20)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default="results/validation/validation.csv")
    a = ap.parse_args()
    rng = random.Random(0)
    sets = {s: 10**6 for s in a.sets} if a.sets else DEFAULT_SETS
    instances = [f for s, k in sets.items() for f in pick(s, k, rng)]
    solvers = ["alg1", "alg2", "cdcl"] + [f"dpllh:{h}" for h in ALL_CODES]
    tasks = [(f, s, a.timeout, 0) for f in instances for s in solvers]
    print(f"{len(instances)} instances x {len(solvers)} solveurs = {len(tasks)} exécutions", file=sys.stderr)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    rows = []
    with ProcessPoolExecutor(a.jobs) as ex:
        for r in ex.map(_task, tasks, chunksize=1):
            rows.append(r)
    keys = sorted({k for r in rows for k in r})
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)

    print(f"{'solveur':12s} {'ok':>5s} {'faux':>5s} {'timeout':>7s} {'modèles vérifiés':>17s}")
    bad = []
    for s in solvers:
        rs = [r for r in rows if r["solver"] == s]
        ok = sum(r["correct"] is True for r in rs)
        ko = [r for r in rs if r["correct"] is False]
        to = sum(r["status"] == "TIMEOUT" for r in rs)
        mv = sum(r["model_ok"] is True for r in rs)
        bad += ko
        print(f"{s:12s} {ok:5d} {len(ko):5d} {to:7d} {mv:17d}")
    # cohérence entre solveurs : jamais deux statuts définitifs contradictoires
    by_inst = {}
    for r in rows:
        if r["status"] != "TIMEOUT":
            by_inst.setdefault(r["instance"], set()).add(r["status"])
    incons = [i for i, st in by_inst.items() if len(st) > 1]
    print(f"\ninstances avec statuts contradictoires entre solveurs : {len(incons)}")
    for r in bad:
        print("ERREUR", r["solver"], r["instance"], r["status"], r["expected"], r["model_ok"])
    return 1 if bad or incons else 0


if __name__ == "__main__":
    sys.exit(main())
