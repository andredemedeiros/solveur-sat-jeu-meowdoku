"""Junction with the SAT solver of part I (question 5).

The solver of part I is used as is, from the `solver/` package (copied from
the part I repository). `solve` runs it on the CNF of an Encoding; the model
it returns is read back with `Encoding.decode`.
"""

from __future__ import annotations

from .encode import Encoding

MODES = ("optimized", "dpll")


def solve(encoding: Encoding, mode: str = "optimized", seed: int = 0):
    """Return (satisfiable, model): model maps variable number -> bool, or None."""
    cnf = encoding.cnf
    if any(len(c) == 0 for c in cnf.clauses):  # a constraint is false: no need for a solver
        return False, None
    if mode == "dpll":
        from solver import dpll
        return dpll.solve(cnf.clauses, cnf.num_vars, seed=seed)
    from solver import portfolio
    return portfolio.solve(cnf.clauses, cnf.num_vars)
