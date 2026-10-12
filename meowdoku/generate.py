"""Question 1 -- Générateur de grilles Meowdoku possédant au moins une solution.

Méthode (« solution plantée ») :

1. Placement des K chats : recherche aléatoire avec retour arrière d'un
   ensemble de K cases deux à deux sur des lignes distinctes, des colonnes
   distinctes et non adjacentes (8-voisinage). Pour N = M = K il s'agit
   d'une permutation σ avec |σ(i) - σ(i+1)| ≥ 2 (existe pour N = 1 et N ≥ 4).
2. Croissance des régions : chaque chat est le germe d'une région ; on fait
   croître simultanément les K régions par un parcours en largeur aléatoire
   (on tire au hasard une case de la frontière commune et on l'attribue à la
   région voisine qui l'a proposée) jusqu'à couvrir la grille. Les régions
   sont connexes, forment une partition, et chacune contient exactement son
   chat germe : le placement de l'étape 1 est une solution PAR CONSTRUCTION.
3. (optionnel, ``unique=True``) Unicité : on cherche avec le solveur une
   seconde solution S' ≠ S (S bloquée par une clause). Si elle existe, on
   choisit une case c de S' \\ S et on la donne à une région voisine, sous
   réserve que sa région d'origine reste connexe. S' devient illicite (sa
   région d'origine perd son chat, la région d'accueil en a deux) tandis que
   S reste licite (c n'est pas un germe). On itère jusqu'à unicité.

``planted=False`` produit au contraire des régions issues de germes
quelconques : la grille peut alors être insatisfiable (utile en Q5).
"""

from __future__ import annotations

import random
import string
from typing import Optional

from .grid import Cell, Grid


def zone_names(k: int) -> list[str]:
    letters = string.ascii_uppercase
    if k <= 26:
        return list(letters[:k])
    names = []
    for a in letters:
        for b in letters:
            names.append(a + b)
    return names[:k]


def place_cats(n: int, m: int, k: int, rng: random.Random, max_tries: int = 200) -> Optional[list[Cell]]:
    """K cases sur lignes/colonnes distinctes, non adjacentes (retour arrière
    aléatoire ligne par ligne sur un sous-ensemble aléatoire de K lignes)."""
    if k > min(n, m):
        return None
    for _ in range(max_tries):
        rows = sorted(rng.sample(range(1, n + 1), k))
        used: set[int] = set()
        sol: list[Cell] = []
        budget = [20000]

        def rec(t: int) -> bool:
            if t == k:
                return True
            budget[0] -= 1
            if budget[0] < 0:
                return False
            i = rows[t]
            cols = list(range(1, m + 1))
            rng.shuffle(cols)
            for j in cols:
                if j in used:
                    continue
                if sol and sol[-1][0] == i - 1 and abs(sol[-1][1] - j) <= 1:
                    continue
                used.add(j)
                sol.append((i, j))
                if rec(t + 1):
                    return True
                sol.pop()
                used.discard(j)
            return False

        if rec(0):
            return sol
    return None


def grow_regions(n: int, m: int, seeds: list[Cell], rng: random.Random) -> list[list[int]]:
    """Croissance aléatoire simultanée ; renvoie owner[i][j] = indice du germe."""
    owner = [[-1] * m for _ in range(n)]
    frontier: list[tuple[int, int, int]] = []
    for r, (i, j) in enumerate(seeds):
        owner[i - 1][j - 1] = r
    for r, (i, j) in enumerate(seeds):
        _push_neighbours(frontier, i - 1, j - 1, r, n, m)
    left = n * m - len(seeds)
    while left:
        idx = rng.randrange(len(frontier))
        frontier[idx], frontier[-1] = frontier[-1], frontier[idx]
        i, j, r = frontier.pop()
        if owner[i][j] != -1:
            continue
        owner[i][j] = r
        left -= 1
        _push_neighbours(frontier, i, j, r, n, m)
    return owner


def _push_neighbours(frontier, i, j, r, n, m):
    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        a, b = i + di, j + dj
        if 0 <= a < n and 0 <= b < m:
            frontier.append((a, b, r))


def _connected_without(owner, region: int, removed: tuple[int, int], seed: tuple[int, int]) -> bool:
    n, m = len(owner), len(owner[0])
    cells = {(i, j) for i in range(n) for j in range(m) if owner[i][j] == region} - {removed}
    if not cells:
        return False
    stack = [seed]
    seen = {seed}
    while stack:
        i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c = (i + di, j + dj)
            if c in cells and c not in seen:
                seen.add(c)
                stack.append(c)
    return len(seen) == len(cells)


def _to_grid(owner, names, comments) -> Grid:
    cells = [[names[r] for r in row] for row in owner]
    return Grid(len(owner), len(owner[0]), list(names), cells, comments)


def other_solution(grid: Grid, avoid: list[Cell]):
    """Une solution de ``grid`` différente de ``avoid`` (ou None)."""
    from solver import cdcl

    from .encode import encode

    cnf, enc = encode(grid)
    clauses = cnf.clauses + [[-enc.var(i, j) for (i, j) in avoid]]
    sat, model = cdcl.solve(clauses, cnf.num_vars)
    return sorted(enc.decode(model)) if sat else None


def generate(n: int, m: Optional[int] = None, k: Optional[int] = None, seed: Optional[int] = None,
             planted: bool = True, unique: bool = False, max_repairs: int = 500) -> tuple[Grid, list[Cell]]:
    """Renvoie (grille, solution plantée) ; solution = [] si planted=False."""
    m = n if m is None else m
    k = n if k is None else k
    rng = random.Random(seed)
    names = zone_names(k)
    comments = [f"Grille generee {n}x{m} K={k} seed={seed}" + (" (planted)" if planted else " (aleatoire)")]
    if not planted:
        all_cells = [(i, j) for i in range(1, n + 1) for j in range(1, m + 1)]
        seeds = rng.sample(all_cells, k)
        return _to_grid(grow_regions(n, m, seeds, rng), names, comments), []

    while True:
        cats = place_cats(n, m, k, rng)
        if cats is None:
            raise ValueError(f"aucun placement de {k} chats possible sur {n}x{m}")
        rng.shuffle(cats)                # nom de région indépendant de la position
        owner = grow_regions(n, m, cats, rng)
        if not unique:
            return _to_grid(owner, names, comments), sorted(cats)
        seed_of = {r: (i - 1, j - 1) for r, (i, j) in enumerate(cats)}
        cat_set = {(i - 1, j - 1) for (i, j) in cats}
        for _ in range(max_repairs):
            grid = _to_grid(owner, names, comments)
            alt = other_solution(grid, cats)
            if alt is None:
                grid.comments.append("solution unique")
                return grid, sorted(cats)
            moved = False
            cand = [(i - 1, j - 1) for (i, j) in alt if (i - 1, j - 1) not in cat_set]
            rng.shuffle(cand)
            for (i, j) in cand:
                r = owner[i][j]
                neigh = {owner[i + di][j + dj] for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))
                         if 0 <= i + di < n and 0 <= j + dj < m} - {r}
                if neigh and _connected_without(owner, r, (i, j), seed_of[r]):
                    owner[i][j] = rng.choice(sorted(neigh))
                    moved = True
                    break
            if not moved:
                break                    # bloqué : on recommence avec un autre placement
