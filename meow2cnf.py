#!/usr/bin/env python3
"""Question 1 -- Conversion d'une grille Meowdoku en fichier DIMACS.

    python meow2cnf.py grille.txt [-o grille.cnf] [--no-redundant] [--amo pairwise|seq]
"""
import argparse
import sys

from meowdoku.encode import encode
from meowdoku.grid import read_grid
from solver.cnf import to_dimacs_string


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("grid")
    ap.add_argument("-o", "--output", help="fichier .cnf (défaut : stdout)")
    ap.add_argument("--no-redundant", action="store_true", help="ne pas ajouter les clauses L>=1 / C>=1")
    ap.add_argument("--amo", choices=["pairwise", "seq"], default="pairwise")
    a = ap.parse_args(argv)
    grid = read_grid(a.grid)
    cnf, enc = encode(grid, redundant=not a.no_redundant, amo=a.amo)
    text = to_dimacs_string(cnf, enc.comments())
    if a.output:
        with open(a.output, "w") as f:
            f.write(text)
        print(f"{a.output} : {cnf.num_vars} variables, {cnf.num_clauses} clauses", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
