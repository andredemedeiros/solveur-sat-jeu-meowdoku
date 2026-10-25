"""Exécution instrumentée d'un solveur sur un fichier DIMACS (validation Q2/Q4,
mesures Q5). Toujours exécutée dans un processus fils (cf. benchmark.py)."""

from __future__ import annotations

import os
import re

from .cnf import check_model, parse_dimacs
from .dpll import Timeout, clock

SOLVERS = ["alg1", "alg2", "cdcl"]  # + "dpllh:<code>"


def expected_status(path: str, cnf=None):
    """Statut attendu : commentaire « status X » (nos instances), sinon le nom
    de fichier SATLIB (uf* / uuf*, *-yes* / *-no*, hole*, dubois*)."""
    if cnf is not None:
        for c in cnf.comments:
            m = re.match(r"status (SAT|UNSAT)", c)
            if m:
                return m.group(1)
    b = os.path.basename(path)
    if b.startswith("uuf") or "-no-" in b or b.startswith(("hole", "dubois", "php")):
        return "UNSAT"
    if b.startswith(("uf", "flat")) or "-yes" in b:
        return "SAT"
    return None


def run_one(path: str, solver: str, timeout: float = 60.0, seed: int = 0) -> dict:
    cnf = parse_dimacs(path)
    res = {"instance": path, "family": os.path.basename(os.path.dirname(path)), "solver": solver,
           "seed": seed, "num_vars": cnf.num_vars, "num_clauses": cnf.num_clauses,
           "expected": expected_status(path, cnf)}
    t0 = clock()
    try:
        if solver == "alg1":
            from . import dpll
            sat, model = dpll.solve_sat(cnf.clauses, seed=seed, timeout=timeout), None
        elif solver == "alg2":
            from . import dpll
            sat, model = dpll.solve(cnf.clauses, cnf.num_vars, seed=seed, timeout=timeout)
        elif solver == "cdcl":
            from .cdcl import CDCL
            s = CDCL(cnf.num_vars, cnf.clauses)
            sat = s.solve(timeout=timeout)
            model = s.model() if sat else None
            res.update(decisions=s.decisions, conflicts=s.conflicts)
        elif solver.startswith("dpllh:"):
            from . import dpll_h, heuristics
            h = solver.split(":", 1)[1]
            d = dpll_h.DPLLH(heuristics.make(h, seed), timeout)
            try:
                sat, model = d.solve(cnf.clauses, cnf.num_vars)
            finally:
                res.update(d.stats.as_dict())
        else:
            raise ValueError(solver)
        res["status"] = "SAT" if sat else "UNSAT"
        res["model_ok"] = check_model(cnf.clauses, model) if model is not None else None
    except (Timeout, TimeoutError):
        res["status"] = "TIMEOUT"
        res["model_ok"] = None
    res["cpu"] = clock() - t0
    exp = res["expected"]
    res["correct"] = None if res["status"] == "TIMEOUT" or exp is None else (
        res["status"] == exp and res["model_ok"] is not False)
    return res
