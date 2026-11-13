#!/usr/bin/env python3
"""Question 6 -- Point d'entrée imposé du solveur.

    python sat.py instance.cnf [--mode dpll|optimized] [--output-model]

  --mode dpll       Algorithme 2 de l'énoncé (DPLL récursif, choix aléatoire)
  --mode optimized  CDCL, relayé après 2 s par un DPLL_H en parallèle
                    (solver/portfolio.py) -- mode par défaut

La sortie standard ne contient que le résultat (« s SATISFIABLE » /
« s UNSATISFIABLE » et, avec --output-model, la ligne « v ... 0 »).
Tout message de diagnostic va sur stderr.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solver.cnf import DimacsError, check_model, model_to_dimacs_line, parse_dimacs  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Solveur SAT (DPLL / CDCL + DPLL)")
    ap.add_argument("instance", help="fichier DIMACS CNF")
    ap.add_argument("--mode", choices=["dpll", "optimized"], default="optimized")
    ap.add_argument("--output-model", action="store_true", help="afficher le modèle (ligne v)")
    ap.add_argument("--seed", type=int, default=0, help="graine du choix aléatoire (mode dpll)")
    ap.add_argument("--verify", action="store_true", help="vérifier le modèle (message sur stderr)")
    args = ap.parse_args(argv)

    try:
        cnf = parse_dimacs(args.instance)
    except (OSError, DimacsError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2

    if args.mode == "dpll":
        from solver import dpll
        sat, model = dpll.solve(cnf.clauses, cnf.num_vars, seed=args.seed)
    else:
        from solver import portfolio
        sat, model = portfolio.solve(cnf.clauses, cnf.num_vars)

    out = ["s SATISFIABLE" if sat else "s UNSATISFIABLE"]
    if sat and args.output_model:
        out.append(model_to_dimacs_line(model, cnf.num_vars))
    sys.stdout.write("\n".join(out) + "\n")
    sys.stdout.flush()
    if sat and args.verify:
        print("c modèle " + ("valide" if check_model(cnf.clauses, model) else "INVALIDE"), file=sys.stderr)
    # Code de retour 0 : l'infrastructure de comparaison lit stdout ; on évite
    # la convention 10/20 des solveurs SAT qui pourrait être prise pour une erreur.
    return 0


if __name__ == "__main__":
    sys.exit(main())
