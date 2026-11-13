"""Question 1 -- Codage d'une grille Meowdoku en formule CNF.

Variables : x_{i,j} (1 ≤ i ≤ N, 1 ≤ j ≤ M) vraie ssi un chat est en (i, j),
numérotée ``var(i, j) = (i-1)·M + j`` (donc 1..N·M, ordre ligne par ligne).

Clauses (codage « par paires », sans variable auxiliaire) :

  (R≥1) pour chaque région R :              ⋁_{c ∈ R} x_c
  (R≤1) pour chaque région R, c ≠ c' ∈ R :  ¬x_c ∨ ¬x_c'
  (L≤1) pour chaque ligne i, j < j' :       ¬x_{i,j} ∨ ¬x_{i,j'}
  (C≤1) pour chaque colonne j, i < i' :     ¬x_{i,j} ∨ ¬x_{i',j}
  (ADJ) voisins diagonaux :                 ¬x_{i,j} ∨ ¬x_{i+1,j±1}
        (les voisins horizontaux / verticaux sont déjà exclus par L≤1/C≤1)

Clauses redondantes optionnelles (``redundant=True``, défaut) : si K = N,
chaque ligne contient exactement un chat (K chats, au plus un par ligne,
N = K lignes : principe des tiroirs) ; on ajoute alors (L≥1) ⋁_j x_{i,j}.
Idem (C≥1) si K = M. Ces clauses ne changent pas l'ensemble des modèles,
mais rendent les déductions « dernière case libre de la ligne » accessibles
à la simple propagation unitaire.

Les clauses identiques produites par plusieurs familles (deux cases d'une
même région ET d'une même ligne) ne sont émises qu'une fois.

Option ``amo="seq"`` : contraintes « au plus un » codées par compteur
séquentiel (Sinz 2005) -- O(n) clauses et variables auxiliaires au lieu de
O(n²) clauses -- pour comparaison sur les grandes grilles.

Remarque : si K > min(N, M) la formule est insatisfiable (au plus un chat
par ligne et par colonne), ce que le solveur établit sans traitement spécial.
"""

from __future__ import annotations

from itertools import combinations

from solver.cnf import CNF

from .grid import Cell, Grid


class Encoder:
    def __init__(self, grid: Grid, redundant: bool = True, amo: str = "pairwise"):
        self.g = grid
        self.redundant = redundant
        self.amo = amo
        self.num_vars = grid.n_rows * grid.n_cols
        self.clauses: list[list[int]] = []
        self._seen: set[tuple[int, ...]] = set()
        self.counts: dict[str, int] = {}

    def var(self, i: int, j: int) -> int:
        return (i - 1) * self.g.n_cols + j

    def cell(self, v: int) -> Cell:
        return (v - 1) // self.g.n_cols + 1, (v - 1) % self.g.n_cols + 1

    def _add(self, family: str, clause: list[int]) -> None:
        key = tuple(sorted(clause))
        if key in self._seen:
            return
        self._seen.add(key)
        self.clauses.append(clause)
        self.counts[family] = self.counts.get(family, 0) + 1

    def _at_most_one(self, family: str, lits: list[int]) -> None:
        if len(lits) < 2:
            return
        if self.amo == "pairwise" or len(lits) <= 4:
            for a, b in combinations(lits, 2):
                self._add(family, [-a, -b])
            return
        # compteur séquentiel : s_k <=> « un des x_1..x_k est vrai »
        n = len(lits)
        s = list(range(self.num_vars + 1, self.num_vars + n))
        self.num_vars += n - 1
        self._add(family, [-lits[0], s[0]])
        for k in range(1, n - 1):
            self._add(family, [-lits[k], s[k]])
            self._add(family, [-s[k - 1], s[k]])
            self._add(family, [-lits[k], -s[k - 1]])
        self._add(family, [-lits[n - 1], -s[n - 2]])

    def encode(self) -> CNF:
        g = self.g
        N, M = g.n_rows, g.n_cols
        for z, cells in g.regions().items():
            self._add("R>=1", [self.var(i, j) for i, j in cells])
        for z, cells in g.regions().items():
            self._at_most_one("R<=1", [self.var(i, j) for i, j in cells])
        for i in range(1, N + 1):
            self._at_most_one("L<=1", [self.var(i, j) for j in range(1, M + 1)])
        for j in range(1, M + 1):
            self._at_most_one("C<=1", [self.var(i, j) for i in range(1, N + 1)])
        for i in range(1, N):
            for j in range(1, M + 1):
                for dj in (-1, 1):
                    if 1 <= j + dj <= M:
                        self._add("ADJ", [-self.var(i, j), -self.var(i + 1, j + dj)])
        if self.redundant:
            if g.K == N:
                for i in range(1, N + 1):
                    self._add("L>=1", [self.var(i, j) for j in range(1, M + 1)])
            if g.K == M:
                for j in range(1, M + 1):
                    self._add("C>=1", [self.var(i, j) for i in range(1, N + 1)])
        return CNF(self.num_vars, self.clauses)

    def comments(self) -> list[str]:
        g = self.g
        lines = [f"Meowdoku {g.n_rows}x{g.n_cols}, {g.K} regions",
                 f"x(i,j) -> (i-1)*{g.n_cols}+j  (variables 1..{g.n_rows * g.n_cols})"]
        if self.num_vars > g.n_rows * g.n_cols:
            lines.append(f"variables {g.n_rows * g.n_cols + 1}..{self.num_vars} : auxiliaires (compteur sequentiel)")
        lines.append("clauses : " + ", ".join(f"{k}={v}" for k, v in self.counts.items()))
        return lines

    def decode(self, model: dict[int, bool]) -> set[Cell]:
        """Valuation témoin -> cases portant un chat."""
        return {self.cell(v) for v in range(1, self.g.n_rows * self.g.n_cols + 1) if model.get(v)}


def encode(grid: Grid, redundant: bool = True, amo: str = "pairwise"):
    """Renvoie (CNF, Encoder) ; l'encodeur sert ensuite au décodage."""
    enc = Encoder(grid, redundant, amo)
    return enc.encode(), enc
