#!/usr/bin/env python3
"""Question 3 -- Résolution d'une grille Meowdoku via le solveur SAT.

    python cli/solve_meowdoku.py grille.txt [-o solution.txt] [--cnf grille.cnf]
                                 [--solver cdcl|dpll|dpllh] [--heuristic H9]

Étapes : grille -> fichier DIMACS (question 1) -> relecture du fichier DIMACS
et résolution par notre solveur -> décodage de la valuation témoin ->
vérification indépendante des règles du jeu -> fichier solution (figure 2).
"""
import argparse
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du dépôt
sys.path.insert(0, ROOT)

from meowdoku.encode import encode  # noqa: E402
from meowdoku.grid import cats_from_cells, check_solution, format_solution, parse_grid_string  # noqa: E402
from solver.cnf import parse_dimacs, write_dimacs  # noqa: E402


def run_solver(name, cnf, heuristic):
    if name == "cdcl":
        from solver import cdcl
        return cdcl.solve(cnf.clauses, cnf.num_vars)
    if name == "dpll":
        from solver import dpll
        return dpll.solve(cnf.clauses, cnf.num_vars, seed=0)
    from solver import dpll_h
    s, m, _ = dpll_h.solve(cnf.clauses, cnf.num_vars, heuristic, seed=0)
    return s, m


def solve_grid_file(path, out=None, cnf_path=None, solver="cdcl", heuristic="H9", redundant=True):
    with open(path, encoding="utf-8") as f:
        source = f.read()
    grid = parse_grid_string(source)
    cnf, enc = encode(grid, redundant=redundant)
    tmp = None
    if cnf_path is None:
        fd, tmp = tempfile.mkstemp(suffix=".cnf")
        os.close(fd)
        cnf_path = tmp
    write_dimacs(cnf, cnf_path, enc.comments())
    try:
        t0 = time.perf_counter()
        sat, model = run_solver(solver, parse_dimacs(cnf_path), heuristic)
        dt = time.perf_counter() - t0
    finally:
        if tmp:
            os.remove(tmp)
    if not sat:
        return None, dt
    cats = cats_from_cells(grid, enc.decode(model))
    errors = check_solution(grid, cats)
    if errors:
        raise AssertionError("solution invalide : " + "; ".join(errors))
    text = format_solution(grid, cats, source)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    return text, dt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("grid")
    ap.add_argument("-o", "--output", help="fichier solution (défaut : stdout)")
    ap.add_argument("--cnf", help="conserver le fichier DIMACS intermédiaire")
    ap.add_argument("--solver", choices=["cdcl", "dpll", "dpllh"], default="cdcl")
    ap.add_argument("--heuristic", default="H9", help="heuristique pour --solver dpllh (H9 : meilleure en Q5)")
    ap.add_argument("--no-redundant", action="store_true")
    a = ap.parse_args(argv)
    text, dt = solve_grid_file(a.grid, a.output, a.cnf, a.solver, a.heuristic, not a.no_redundant)
    if text is None:
        print("Grille sans solution (formule UNSAT).", file=sys.stderr)
        return 1
    if not a.output:
        sys.stdout.write(text)
    print(f"solution vérifiée ({dt:.3f} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
