#!/usr/bin/env python3
"""Génération des jeux d'instances DIMACS utilisés en questions 2, 4 et 5.

    python experiments/gen_cnf.py [--outdir data/generated/cnf]

Familles produites (en plus des instances SATLIB de data/satlib) :
  rand3/      3-SAT aléatoire uniforme, n ∈ {20,30,40,50}, ratio m/n ∈ {3, 4.26, 5.5}
  php/        principe des tiroirs PHP(n+1, n), n = 3..7 (UNSAT, durs pour la résolution)
  meow_sat/   grilles Meowdoku à solution plantée (N = M = K = 5..24), codage complet
  meow_nored/ mêmes grilles, sans clauses redondantes L>=1/C>=1
  meow_rnd/   grilles à régions aléatoires (N = 6..16) : SAT ou UNSAT
Le statut attendu (SAT/UNSAT) est calculé avec pycosat (solveur de référence
indépendant) et écrit en commentaire « c status SAT|UNSAT ».
"""
import argparse
import os
import sys
import random

import pycosat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du dépôt
sys.path.insert(0, ROOT)

from meowdoku.encode import encode  # noqa: E402
from meowdoku.generate import generate  # noqa: E402
from meowdoku.grid import format_grid  # noqa: E402
from solver.cnf import CNF, write_dimacs  # noqa: E402


def status(cnf):
    return "UNSAT" if pycosat.solve(cnf.clauses) == "UNSAT" else "SAT"


def rand3(n, ratio, rng):
    m = round(n * ratio)
    clauses = []
    for _ in range(m):
        vs = rng.sample(range(1, n + 1), 3)
        clauses.append([v if rng.random() < 0.5 else -v for v in vs])
    return CNF(n, clauses)


def php(n):
    """n+1 pigeons, n trous ; p(i,j) = pigeon i dans le trou j."""
    var = lambda i, j: (i - 1) * n + j
    clauses = [[var(i, j) for j in range(1, n + 1)] for i in range(1, n + 2)]
    for j in range(1, n + 1):
        for i in range(1, n + 2):
            for k in range(i + 1, n + 2):
                clauses.append([-var(i, j), -var(k, j)])
    return CNF((n + 1) * n, clauses)


def save(cnf, path, comments):
    st = status(cnf)
    write_dimacs(cnf, path, comments + [f"status {st}"])
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/generated/cnf")
    ap.add_argument("--griddir", default="data/generated/grids")
    a = ap.parse_args()
    rng = random.Random(2026)
    for d in ("rand3", "php", "meow_sat", "meow_nored", "meow_rnd"):
        os.makedirs(os.path.join(a.outdir, d), exist_ok=True)
    os.makedirs(a.griddir, exist_ok=True)

    for n in (20, 30, 40, 50):
        for ratio in (3.0, 4.26, 5.5):
            for i in range(5):
                cnf = rand3(n, ratio, rng)
                p = os.path.join(a.outdir, "rand3", f"r3_n{n}_r{ratio}_{i}.cnf")
                save(cnf, p, [f"3-SAT aleatoire n={n} ratio={ratio}"])
    for n in range(3, 8):
        save(php(n), os.path.join(a.outdir, "php", f"php_{n + 1}_{n}.cnf"), [f"PHP({n + 1},{n})"])

    for N in (5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 24):
        for i in range(3):
            seed = 1000 * N + i
            grid, _ = generate(N, seed=seed)
            name = f"meow_{N}x{N}_{i}"
            with open(os.path.join(a.griddir, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(format_grid(grid))
            for sub, red in (("meow_sat", True), ("meow_nored", False)):
                cnf, enc = encode(grid, redundant=red)
                save(cnf, os.path.join(a.outdir, sub, name + ".cnf"), enc.comments())
    for N in (6, 7, 8, 9, 10, 12, 14, 16):
        for i in range(5):
            grid, _ = generate(N, seed=5000 * N + i, planted=False)
            name = f"rnd_{N}x{N}_{i}"
            with open(os.path.join(a.griddir, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(format_grid(grid))
            cnf, enc = encode(grid)
            st = save(cnf, os.path.join(a.outdir, "meow_rnd", name + ".cnf"), enc.comments())
            print(name, st)


if __name__ == "__main__":
    main()
