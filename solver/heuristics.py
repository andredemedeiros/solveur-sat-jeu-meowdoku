"""Question 4 -- Heuristiques de branchement pour DPLL_H.

Chaque heuristique est un objet exposant :

* ``prepare(F)``  : appelé une fois sur la formule initiale (pré-traitement
  des versions statiques : calcul d'un ordre a priori) ;
* ``choose(F, lits)`` : appelé à chaque décision (ligne 17 de l'algorithme 3)
  avec la formule courante ``F`` et l'ensemble ``lits`` de ses littéraux
  (déjà calculé par la boucle principale pour la règle du littéral pur).
  Renvoie ``(p, b)`` : variable et valeur de vérité.

« Variable non encore affectée » = variable apparaissant dans la formule
courante : une variable absente de F est soit affectée, soit sans influence
(F[p <- b] = F), la choisir serait une décision inutile.

Départage des ex aequo : plus petit indice de variable (ordre DIMACS), sauf
mention contraire, de sorte que toutes les heuristiques sont déterministes.

Comptage : ``collections.Counter.update`` compte les littéraux d'un
itérable en C, ce qui rend les versions dynamiques nettement moins coûteuses
qu'une double boucle Python.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Optional

# --------------------------------------------------------------------------- #
# Comptages
# --------------------------------------------------------------------------- #

def lit_counts(F) -> Counter:
    """occ(l, F) pour tout littéral l."""
    cnt: Counter = Counter()
    upd = cnt.update
    for c in F:
        upd(c)
    return cnt


def lit_counts_min_size(F, ignore_units: bool = False):
    """(k, occ_k(·, F)) avec k = taille minimale des clauses (≥ 2 si
    ``ignore_units``)."""
    sizes = [len(c) for c in F if not ignore_units or len(c) > 1]
    if not sizes:
        return 0, Counter()
    k = min(sizes)
    cnt: Counter = Counter()
    upd = cnt.update
    for c in F:
        if len(c) == k:
            upd(c)
    return k, cnt


def jw_scores(F) -> dict:
    """J(l) = Σ_k occ_k(l, F) · 2^-k  (Jeroslow-Wang).
    Les clauses sont regroupées par taille : un Counter (C) par taille, puis
    combinaison pondérée -- bien plus rapide qu'une boucle par littéral."""
    by_size: dict[int, Counter] = {}
    for c in F:
        n = len(c)
        cnt = by_size.get(n)
        if cnt is None:
            cnt = by_size[n] = Counter()
        cnt.update(c)
    score: dict[int, float] = {}
    for n, cnt in by_size.items():
        w = 2.0 ** -n
        for l, k in cnt.items():
            score[l] = score.get(l, 0.0) + k * w
    return score


def _best_var(cnt, variables):
    """argmax_p (cnt[p] + cnt[-p]) ; valeur = polarité majoritaire (≥ -> 1)."""
    best = None
    best_key = None
    get = cnt.get
    for p in variables:
        pos = get(p, 0)
        neg = get(-p, 0)
        key = (pos + neg, -p)
        if best_key is None or key > best_key:
            best_key, best = key, (p, pos >= neg)
    return best


def _best_lit(cnt, lits):
    best = None
    best_key = None
    get = cnt.get
    for l in lits:
        key = (get(l, 0), -abs(l), l > 0)
        if best_key is None or key > best_key:
            best_key, best = key, l
    return abs(best), best > 0


# --------------------------------------------------------------------------- #
# Classes
# --------------------------------------------------------------------------- #

class Heuristic:
    name = "?"
    code = "?"
    dynamic = True

    def prepare(self, F) -> None:
        pass

    def choose(self, F, lits: set[int]):
        raise NotImplementedError

    def __repr__(self) -> str:
        return self.name


class RandomChoice(Heuristic):
    """H0 -- Choix Aléatoire (CA) : identique à RandomChoice de l'algorithme 2."""
    code, name = "H0", "CA"

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)

    def choose(self, F, lits):
        p = self.rng.choice(list({abs(l) for l in lits}))
        return p, self.rng.random() < 0.5


class FirstFree(Heuristic):
    """H1 -- Première Variable Libre (PVL) : plus petit indice, valeur 1."""
    code, name = "H1", "PVL"
    dynamic = False

    def choose(self, F, lits):
        return min(abs(l) for l in lits), True


class StaticOrder(Heuristic):
    """Version statique générique : un ordre de (variable, valeur) calculé sur
    la formule initiale ; la décision prend la première variable de l'ordre
    encore présente dans F. Le pointeur ``pos`` n'avance jamais au-delà d'une
    variable présente ; on le recalcule depuis le début à chaque appel car,
    après un retour arrière, une variable « passée » peut redevenir libre."""
    dynamic = False

    def __init__(self):
        self.order: list[tuple[int, bool]] = []

    def score_order(self, F) -> list[tuple[int, bool]]:
        raise NotImplementedError

    def prepare(self, F):
        self.order = self.score_order(F)

    def choose(self, F, lits):
        for p, b in self.order:
            if p in lits or -p in lits:
                return p, b
        # variable absente de la formule initiale (n'arrive pas en pratique)
        return min(abs(l) for l in lits), True


# ---------------- H2 : VPPM ------------------------------------------------- #
def _order_vars(cnt, extra=None):
    vars_ = {abs(l) for l in cnt}
    key = (lambda p: (-(cnt[p] + cnt[-p]), p)) if extra is None else \
          (lambda p: (-(cnt[p] + cnt[-p]), -(extra[p] + extra[-p]), p))
    return [(p, cnt[p] >= cnt[-p]) for p in sorted(vars_, key=key)]


class VPPMStatic(StaticOrder):
    code, name = "H2s", "VPPM-s"

    def score_order(self, F):
        return _order_vars(lit_counts(F))


class VPPMDynamic(Heuristic):
    code, name = "H2d", "VPPM-d"

    def choose(self, F, lits):
        cnt = lit_counts(F)
        return _best_var(cnt, {abs(l) for l in lits})


# ---------------- H3 : LP --------------------------------------------------- #
class LPStatic(StaticOrder):
    code, name = "H3s", "LP-s"

    def score_order(self, F):
        cnt = lit_counts(F)
        lits = sorted(cnt, key=lambda l: (-cnt[l], abs(l), l < 0))
        seen, order = set(), []
        for l in lits:  # un même p n'apparaît qu'une fois (son meilleur littéral)
            if abs(l) not in seen:
                seen.add(abs(l))
                order.append((abs(l), l > 0))
        return order


class LPDynamic(Heuristic):
    code, name = "H3d", "LP-d"

    def choose(self, F, lits):
        return _best_lit(lit_counts(F), lits)


# ---------------- H4 : VFCM (MOMS) ------------------------------------------ #
# Départage secondaire par #(p, F) : sur une formule où peu de variables
# figurent dans les clauses de taille minimale, l'ordre resterait sinon
# purement lexicographique pour la majorité d'entre elles.
class VFCMStatic(StaticOrder):
    code, name = "H4s", "VFCM-s"

    def score_order(self, F):
        # Les clauses unitaires initiales sont propagées avant toute décision :
        # k est la taille minimale des clauses non unitaires.
        _, cnt_k = lit_counts_min_size(F, ignore_units=True)
        cnt = lit_counts(F)
        vars_ = {abs(l) for l in cnt}
        key = lambda p: (-(cnt_k[p] + cnt_k[-p]), -(cnt[p] + cnt[-p]), p)
        return [(p, cnt_k[p] >= cnt_k[-p] if cnt_k[p] + cnt_k[-p] else cnt[p] >= cnt[-p])
                for p in sorted(vars_, key=key)]


class VFCMDynamic(Heuristic):
    code, name = "H4d", "VFCM-d"

    def choose(self, F, lits):
        _, cnt = lit_counts_min_size(F)
        cand = {abs(l) for l in cnt}
        return _best_var(cnt, cand)


# ---------------- H5 : LFCM ------------------------------------------------- #
class LFCMStatic(StaticOrder):
    code, name = "H5s", "LFCM-s"

    def score_order(self, F):
        _, cnt_k = lit_counts_min_size(F, ignore_units=True)
        cnt = lit_counts(F)
        lits = sorted(cnt, key=lambda l: (-cnt_k[l], -cnt[l], abs(l), l < 0))
        seen, order = set(), []
        for l in lits:
            if abs(l) not in seen:
                seen.add(abs(l))
                order.append((abs(l), l > 0))
        return order


class LFCMDynamic(Heuristic):
    code, name = "H5d", "LFCM-d"

    def choose(self, F, lits):
        _, cnt = lit_counts_min_size(F)
        return _best_lit(cnt, set(cnt))


# ---------------- H6 : VJW -------------------------------------------------- #
class VJWStatic(StaticOrder):
    code, name = "H6s", "VJW-s"

    def score_order(self, F):
        s = jw_scores(F)
        vars_ = {abs(l) for l in s}
        g = s.get
        key = lambda p: (-(g(p, 0) + g(-p, 0)), p)
        return [(p, g(p, 0) >= g(-p, 0)) for p in sorted(vars_, key=key)]


class VJWDynamic(Heuristic):
    code, name = "H6d", "VJW-d"

    def choose(self, F, lits):
        return _best_var(jw_scores(F), {abs(l) for l in lits})


# ---------------- H7 : LJW -------------------------------------------------- #
class LJWStatic(StaticOrder):
    code, name = "H7s", "LJW-s"

    def score_order(self, F):
        s = jw_scores(F)
        lits = sorted(s, key=lambda l: (-s[l], abs(l), l < 0))
        seen, order = set(), []
        for l in lits:
            if abs(l) not in seen:
                seen.add(abs(l))
                order.append((abs(l), l > 0))
        return order


class LJWDynamic(Heuristic):
    code, name = "H7d", "LJW-d"

    def choose(self, F, lits):
        return _best_lit(jw_scores(F), lits)


# ---------------- H8 : heuristique personnelle (MOMS « produit ») ----------- #
class MOMSProduct(Heuristic):
    """H8 -- MOMS à score produit (inspirée de POSIT, Freeman 1995).

    Sur les clauses de taille minimale k, score(p) = occ_k(p)·occ_k(¬p)·2^10
    + occ_k(p) + occ_k(¬p). Le produit favorise les variables présentes avec
    les DEUX polarités : chaque branche (p et ¬p) raccourcit alors beaucoup de
    clauses minimales, donc provoque des propagations unitaires des deux côtés
    -- c'est ce qui réduit l'arbre lorsque l'on doit explorer les deux
    branches (instances UNSAT). Valeur : polarité majoritaire (comme VFCM),
    qui satisfait le plus de clauses minimales et favorise les instances SAT."""
    code, name = "H8", "MOMS-P"

    def choose(self, F, lits):
        _, cnt = lit_counts_min_size(F)
        get = cnt.get
        best, best_key = None, None
        for p in {abs(l) for l in cnt}:
            a, b = get(p, 0), get(-p, 0)
            key = (a * b * 1024 + a + b, -p)
            if best_key is None or key > best_key:
                best_key, best = key, (p, a >= b)
        return best


# ---------------- H9 : heuristique personnelle (plus petite clause positive) - #
class MRV(Heuristic):
    """H9 -- « Minimum Remaining Values » : choisir la plus petite clause dont
    tous les littéraux sont positifs, et y affecter à 1 la variable « la moins
    contraignante » : celle dont le littéral négatif apparaît le moins dans
    les clauses binaires (poser ce chat élimine le moins d'autres cases).

    Motivation (observée en Q5 sur Meowdoku) : les clauses positives sont
    exactement les contraintes « au moins un chat » (région, ligne, colonne) ;
    la plus courte correspond à la région/ligne/colonne ayant le moins de
    cases encore possibles -- l'heuristique MRV des solveurs de contraintes.
    Affecter x = 1 (poser un chat) déclenche, via les clauses binaires
    « au plus un » et d'adjacence, une cascade de propagations unitaires,
    alors qu'une décision x = 0 (choisie par les heuristiques à polarité
    majoritaire, les littéraux négatifs étant majoritaires) n'apporte presque
    rien. Si aucune clause n'est entièrement positive, on se replie sur H6d.
    Le choix « moins contraignante » a été retenu après essai (Q5) : sur les
    grilles 16..24 et aléatoires 12..16, PAR-2 de 15 s contre 30 s pour « plus
    petit indice » et 71 s pour « plus contraignante ».
    Coût : deux parcours de F."""
    code, name = "H9", "MRV"

    def __init__(self):
        self.fallback = VJWDynamic()

    def choose(self, F, lits):
        best = None
        bl = 1 << 30
        for c in F:
            n = len(c)
            if n < bl:
                for l in c:
                    if l < 0:
                        break
                else:
                    best, bl = c, n
                    if n == 2:
                        break
        if best is None:
            return self.fallback.choose(F, lits)
        neg: Counter = Counter()
        upd = neg.update
        for c in F:
            if len(c) == 2:
                upd(c)
        return min(best, key=lambda l: (neg.get(-l, 0), l)), True


REGISTRY = {
    "H0": RandomChoice, "CA": RandomChoice,
    "H1": FirstFree, "PVL": FirstFree,
    "H2s": VPPMStatic, "H2d": VPPMDynamic,
    "H3s": LPStatic, "H3d": LPDynamic,
    "H4s": VFCMStatic, "H4d": VFCMDynamic,
    "H5s": LFCMStatic, "H5d": LFCMDynamic,
    "H6s": VJWStatic, "H6d": VJWDynamic,
    "H7s": LJWStatic, "H7d": LJWDynamic,
    "H8": MOMSProduct,
    "H9": MRV,
}

ALL_CODES = ["H0", "H1", "H2s", "H2d", "H3s", "H3d", "H4s", "H4d",
             "H5s", "H5d", "H6s", "H6d", "H7s", "H7d", "H8", "H9"]


def make(code: str, seed: Optional[int] = None) -> Heuristic:
    cls = REGISTRY[code]
    return cls(seed) if cls is RandomChoice else cls()
