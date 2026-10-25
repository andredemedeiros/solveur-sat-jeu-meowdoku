"""Question 2.2 -- Algorithmes 1 et 2 (DPLL « du cours »).

Implémentation volontairement fidèle au pseudo-code de l'énoncé :
récursive, avec simplification explicite F[l <- 1] qui construit une
nouvelle formule à chaque appel (pas d'effet de bord, pas de retour arrière
à gérer : la formule du père reste intacte).

Représentation : une formule est une ``list[frozenset[int]]``.
  * ``l in C`` et ``C - {¬l}`` sont en O(1) / O(|C|) ;
  * le frozenset élimine d'office les doublons de littéraux ;
  * les clauses non touchées par une affectation sont partagées (pas de copie).
"""

from __future__ import annotations

import random
import sys
import threading
import time
from typing import Callable, Iterable, Optional, TypeVar

Formula = list  # list[frozenset[int]]
T = TypeVar("T")


class Timeout(Exception):
    """Levée lorsque la limite de temps donnée au solveur est atteinte."""


# Horloge des mesures (Q5) : temps CPU du processus, sauf sous Windows où
# process_time n'avance que par pas de 15,6 ms (la plupart des exécutions
# mesureraient 0) ; on y prend perf_counter, chaque mesure étant faite seule
# dans un processus fils sans entrées/sorties (temps réel ≈ temps CPU).
clock = time.perf_counter if sys.platform == "win32" else time.process_time


# --------------------------------------------------------------------------- #
# Outils communs
# --------------------------------------------------------------------------- #
def make_formula(clauses: Iterable[Iterable[int]]) -> Formula:
    """Clauses DIMACS -> formule. Les clauses tautologiques (p ∨ ¬p) sont
    supprimées : elles sont toujours vraies et fausseraient la règle du
    littéral pur."""
    F = []
    for c in clauses:
        s = frozenset(c)
        if any(-l in s for l in s):
            continue
        F.append(s)
    return F


def assign(F: Formula, lit: int) -> Formula:
    """F[lit <- 1] : supprime les clauses contenant lit, retire ¬lit des autres.
    (F[p <- 0] s'écrit donc assign(F, -p).)"""
    neg = -lit
    out = []
    append = out.append
    for c in F:
        if lit in c:
            continue
        if neg in c:
            append(c - {neg})
        else:
            append(c)
    return out


EMPTY = object()


def scan(F: Formula):
    """Une seule passe sur F pour les lignes 1-11 de l'algorithme :
    renvoie EMPTY si F contient la clause vide, sinon (unit, lits) où
    ``unit`` est un littéral d'une clause unitaire (ou None) et ``lits``
    l'ensemble des littéraux de F."""
    unit = None
    lits: set[int] = set()
    for c in F:
        n = len(c)
        if n == 0:
            return EMPTY
        if n == 1 and unit is None:
            for unit in c:
                pass
        lits |= c
    return unit, lits


def find_pure(lits: set[int]) -> Optional[int]:
    for l in lits:
        if -l not in lits:
            return l
    return None


def run_deep(fn: Callable[[], T], stack_mb: int = 512) -> T:
    """Exécute ``fn`` dans un thread à grosse pile : la profondeur de récursion
    de DPLL peut atteindre le nombre de variables. Windows refuse une pile
    > 256 Mo : on réessaie avec des tailles décroissantes."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 1_000_000))
    old = threading.stack_size()
    for mb in (stack_mb, 256, 128, 64):
        try:
            threading.stack_size(mb * 1024 * 1024)
            break
        except ValueError:
            continue
    box: dict = {}

    def target():
        try:
            box["r"] = fn()
        except BaseException as e:  # propagé au thread appelant
            box["e"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join()
    threading.stack_size(old)
    if "e" in box:
        raise box["e"]
    return box["r"]


# --------------------------------------------------------------------------- #
# Algorithme 1 : satisfiabilité seule
# --------------------------------------------------------------------------- #
def dpll1(F: Formula, rng: random.Random, deadline: float = float("inf")) -> bool:
    if time.perf_counter() > deadline:
        raise Timeout
    r = scan(F)
    if r is EMPTY:                       # ligne 1
        return False
    if not F:                            # ligne 3
        return True
    unit, lits = r
    if unit is not None:                 # ligne 5
        return dpll1(assign(F, unit), rng, deadline)
    pure = find_pure(lits)
    if pure is not None:                 # ligne 7
        return dpll1(assign(F, pure), rng, deadline)
    p = rng.choice(list({abs(l) for l in lits}))   # ligne 9
    lit = p if rng.random() < 0.5 else -p
    if dpll1(assign(F, lit), rng, deadline):       # ligne 10
        return True
    return dpll1(assign(F, -lit), rng, deadline)   # ligne 13


# --------------------------------------------------------------------------- #
# Algorithme 2 : satisfiabilité + valuation témoin
# --------------------------------------------------------------------------- #
# La valuation est un dict {variable: bool}. « v ∪ {l} » ajoute l'association
# correspondant au littéral l. Le dict est construit en remontant la récursion
# (le même objet est enrichi : pas de copie).

def dpll2(F: Formula, rng: random.Random, deadline: float = float("inf")):
    if time.perf_counter() > deadline:
        raise Timeout
    r = scan(F)
    if r is EMPTY:
        return False, None
    if not F:
        return True, {}
    unit, lits = r
    if unit is not None:
        s, v = dpll2(assign(F, unit), rng, deadline)
        if s:
            v[abs(unit)] = unit > 0
            return True, v
        return False, None
    pure = find_pure(lits)
    if pure is not None:
        s, v = dpll2(assign(F, pure), rng, deadline)
        if s:
            v[abs(pure)] = pure > 0
            return True, v
        return False, None
    p, b = random_choice(lits, rng)
    lit = p if b else -p
    s, v = dpll2(assign(F, lit), rng, deadline)
    if s:
        v[p] = b
        return True, v
    s, v = dpll2(assign(F, -lit), rng, deadline)
    if s:
        v[p] = not b
        return True, v
    return False, None


def random_choice(lits: set[int], rng: random.Random):
    """RandomChoice(F) : variable uniforme parmi celles de F, valeur uniforme."""
    p = rng.choice(list({abs(l) for l in lits}))
    return p, rng.random() < 0.5


# --------------------------------------------------------------------------- #
# Points d'entrée
# --------------------------------------------------------------------------- #
def solve_sat(clauses, seed: Optional[int] = None, timeout: float = float("inf")) -> bool:
    """Algorithme 1 sur une liste de clauses DIMACS."""
    F = make_formula(clauses)
    rng = random.Random(seed)
    deadline = time.perf_counter() + timeout
    return run_deep(lambda: dpll1(F, rng, deadline))


def solve(clauses, num_vars: int, seed: Optional[int] = None, timeout: float = float("inf")):
    """Algorithme 2 : renvoie (sat, modèle complet ou None)."""
    from .cnf import complete_model

    F = make_formula(clauses)
    rng = random.Random(seed)
    deadline = time.perf_counter() + timeout
    s, v = run_deep(lambda: dpll2(F, rng, deadline))
    return s, (complete_model(v, num_vars) if s else None)
