#!/usr/bin/env python3
"""Question 1 -- Génération de grilles Meowdoku ayant au moins une solution.

    python generate_grids.py N [--M M] [--K K] [--count 10] [--seed 0]
                             [--unique] [--random] [-o data/grids/gen]

  --unique  impose l'unicité de la solution (réparations successives)
  --random  régions à germes aléatoires : AUCUNE garantie de solution
            (sert à produire des instances UNSAT pour la question 5)
Chaque grille est écrite dans <dir>/meow_<N>x<M>_k<K>_<i>.txt ; pour les
grilles plantées, la solution plantée est écrite à côté (*.planted.txt).
"""
import argparse
import os
import sys

from meowdoku.generate import generate
from meowdoku.grid import format_grid, format_solution


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("N", type=int)
    ap.add_argument("--M", type=int)
    ap.add_argument("--K", type=int)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--unique", action="store_true")
    ap.add_argument("--random", action="store_true")
    ap.add_argument("-o", "--outdir", default="data/grids/gen")
    a = ap.parse_args(argv)
    M = a.M or a.N
    K = a.K or a.N
    os.makedirs(a.outdir, exist_ok=True)
    tag = "rnd" if a.random else ("uniq" if a.unique else "meow")
    for i in range(a.count):
        seed = a.seed * 100003 + i
        grid, sol = generate(a.N, M, K, seed=seed, planted=not a.random, unique=a.unique)
        path = os.path.join(a.outdir, f"{tag}_{a.N}x{M}_k{K}_{i:03d}.txt")
        with open(path, "w") as f:
            f.write(format_grid(grid))
        if sol:
            cats = {grid.zone_of(c): c for c in sol}
            with open(path[:-4] + ".planted.txt", "w") as f:
                f.write(format_solution(grid, cats))
        print(path, file=sys.stderr)


if __name__ == "__main__":
    main()
