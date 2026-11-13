"""Questions 4 et 5 -- Algorithme 3 (DPLL_H) instrumenté.

Même structure que dpll2 (dpll.py), la fonction RandomChoice étant remplacée
par ``heuristic.choose``. Les compteurs demandés en question 5 sont tenus
dans un objet :class:`Stats` :

  decisions   -- exécutions de la ligne 17 (choix heuristique)
  backtracks  -- exécutions de la branche else (ligne 21)
  unit_props  -- applications de la règle de la clause unitaire (ligne 5)
  pure_lits   -- applications de la règle du littéral pur (ligne 11)
  conflicts   -- appels rencontrant la clause vide (feuilles d'échec)
  nodes       -- nombre total d'appels récursifs
  max_depth   -- profondeur maximale de récursion
  time_total  -- temps CPU total (``dpll.clock``)
  time_heur   -- temps CPU passé dans ``heuristic.prepare`` + ``choose``
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .dpll import EMPTY, Timeout, assign, clock, find_pure, make_formula, run_deep, scan
from . import heuristics as H


@dataclass
class Stats:
    decisions: int = 0
    backtracks: int = 0
    unit_props: int = 0
    pure_lits: int = 0
    conflicts: int = 0
    nodes: int = 0
    max_depth: int = 0
    time_total: float = 0.0
    time_heur: float = 0.0

    @property
    def heur_ratio(self) -> float:
        return self.time_heur / self.time_total if self.time_total > 0 else 0.0

    def as_dict(self) -> dict:
        d = asdict(self)
        d["heur_ratio"] = self.heur_ratio
        return d


class DPLLH:
    def __init__(self, heuristic: H.Heuristic, timeout: float = float("inf")):
        self.h = heuristic
        self.timeout = timeout
        self.stats = Stats()

    # ------------------------------------------------------------------ #
    def _rec(self, F, depth):
        st = self.stats
        st.nodes += 1
        if depth > st.max_depth:
            st.max_depth = depth
        if not st.nodes & 63 and clock() > self.deadline:   # contrôle tous les 64 nœuds
            raise Timeout
        r = scan(F)
        if r is EMPTY:                                   # ligne 1
            st.conflicts += 1
            return False, None
        if not F:                                        # ligne 3
            return True, {}
        unit, lits = r
        if unit is not None:                             # ligne 5
            st.unit_props += 1
            s, v = self._rec(assign(F, unit), depth + 1)
            if s:
                v[abs(unit)] = unit > 0
                return True, v
            return False, None
        pure = find_pure(lits)
        if pure is not None:                             # ligne 11
            st.pure_lits += 1
            s, v = self._rec(assign(F, pure), depth + 1)
            if s:
                v[abs(pure)] = pure > 0
                return True, v
            return False, None
        st.decisions += 1                                # ligne 17
        t0 = clock()
        p, b = self.h.choose(F, lits)
        st.time_heur += clock() - t0
        lit = p if b else -p
        s, v = self._rec(assign(F, lit), depth + 1)      # ligne 18
        if s:
            v[p] = b
            return True, v
        st.backtracks += 1                               # ligne 21
        s, v = self._rec(assign(F, -lit), depth + 1)
        if s:
            v[p] = not b
            return True, v
        return False, None

    # ------------------------------------------------------------------ #
    def solve(self, clauses, num_vars: int):
        """Renvoie (sat, modèle complet ou None). Lève Timeout si la limite de
        temps CPU est dépassée (les statistiques restent consultables)."""
        from .cnf import complete_model

        F = make_formula(clauses)
        t_start = clock()
        self.deadline = t_start + self.timeout
        try:
            t0 = clock()
            self.h.prepare(F)
            self.stats.time_heur += clock() - t0
            s, v = run_deep(lambda: self._rec(F, 0))
        finally:
            self.stats.time_total = clock() - t_start
        return s, (complete_model(v, num_vars) if s else None)


def solve(clauses, num_vars: int, heuristic: str = "H0", seed=None, timeout=float("inf")):
    solver = DPLLH(H.make(heuristic, seed), timeout)
    s, m = solver.solve(clauses, num_vars)
    return s, m, solver.stats
