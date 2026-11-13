"""Grilles Meowdoku : lecture/écriture des fichiers grille et solution,
vérification indépendante d'une solution (questions 1 et 3)."""

from __future__ import annotations

from dataclasses import dataclass, field

Cell = tuple[int, int]  # (ligne, colonne), indices à partir de 1


class GridError(ValueError):
    pass


@dataclass
class Grid:
    n_rows: int
    n_cols: int
    zones: list[str]
    cells: list[list[str]]                 # cells[i][j] : nom de la région (indices 0)
    comments: list[str] = field(default_factory=list)

    @property
    def K(self) -> int:
        return len(self.zones)

    def zone_of(self, cell: Cell) -> str:
        i, j = cell
        return self.cells[i - 1][j - 1]

    def regions(self) -> dict[str, list[Cell]]:
        reg: dict[str, list[Cell]] = {z: [] for z in self.zones}
        for i in range(self.n_rows):
            for j in range(self.n_cols):
                reg[self.cells[i][j]].append((i + 1, j + 1))
        return reg


# --------------------------------------------------------------------------- #
# Lecture
# --------------------------------------------------------------------------- #
def _is_comment(line: str, zones: set[str] | None) -> bool:
    # Une ligne commençant par 'c' est un commentaire, sauf si (cas limite)
    # 'c' est le nom d'une région déclarée et qu'on lit une ligne de la grille.
    if not line.startswith("c"):
        return False
    return zones is None or line.split()[0] not in zones


def _parse(lines: list[str]):
    """Analyse l'en-tête et la grille ; renvoie (Grid, lignes restantes)."""
    n = m = None
    zones: list[str] | None = None
    comments: list[str] = []
    rows: list[list[str]] = []
    k = 0
    while k < len(lines):
        line = lines[k].strip()
        k += 1
        if not line:
            continue
        if _is_comment(line, set(zones) if zones else None):
            comments.append(line[1:].strip())
            continue
        tok = line.split()
        if tok[0] == "GRID":
            if len(tok) != 3:
                raise GridError(f"ligne GRID invalide : {line!r}")
            n, m = int(tok[1]), int(tok[2])
        elif tok[0] == "ZONES":
            zones = tok[1:]
            if len(set(zones)) != len(zones):
                raise GridError("noms de régions dupliqués")
        else:
            if n is None or zones is None:
                raise GridError("GRID et ZONES doivent précéder la grille")
            if len(tok) != m:
                raise GridError(f"ligne {len(rows) + 1} : {len(tok)} cases au lieu de {m}")
            unknown = set(tok) - set(zones)
            if unknown:
                raise GridError(f"régions non déclarées : {sorted(unknown)}")
            rows.append(tok)
            if len(rows) == n:
                break
    if n is None or zones is None or len(rows) != n:
        raise GridError("grille incomplète")
    present = {z for r in rows for z in r}
    empty = [z for z in zones if z not in present]
    if empty:
        raise GridError(f"régions vides : {empty}")
    return Grid(n, m, zones, rows, comments), lines[k:]


def parse_grid_string(text: str) -> Grid:
    return _parse(text.splitlines())[0]


def read_grid(path: str) -> Grid:
    with open(path, encoding="utf-8") as f:
        return parse_grid_string(f.read())


def parse_solution_string(text: str):
    """Fichier solution (figure 2) -> (Grid, {région: (i, j)}, grille de * )."""
    grid, rest = _parse(text.splitlines())
    rest = [l.strip() for l in rest if l.strip()]
    cats: dict[str, Cell] = {}
    zones = set(grid.zones)
    idx = 0
    while idx < len(rest) and rest[idx].split()[0] in zones and len(rest[idx].split()) == 3:
        z, i, j = rest[idx].split()
        cats[z] = (int(i), int(j))
        idx += 1
    stars = [r.split() for r in rest[idx: idx + grid.n_rows]]
    return grid, cats, stars


def read_solution(path: str):
    with open(path, encoding="utf-8") as f:
        return parse_solution_string(f.read())


# --------------------------------------------------------------------------- #
# Écriture
# --------------------------------------------------------------------------- #
def format_grid(grid: Grid) -> str:
    out = [f"c {c}" for c in grid.comments]
    out.append(f"GRID {grid.n_rows} {grid.n_cols}")
    out.append("ZONES " + " ".join(grid.zones))
    out.append("")
    out.extend(" ".join(r) for r in grid.cells)
    return "\n".join(out) + "\n"


def write_grid(grid: Grid, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(format_grid(grid))


def format_solution(grid: Grid, cats: dict[str, Cell], source_text: str | None = None) -> str:
    """Recopie la grille d'entrée puis donne la solution sous deux formes :
    dictionnaire région -> (ligne, colonne) et grille marquée par *."""
    head = source_text.rstrip("\n") if source_text is not None else format_grid(grid).rstrip("\n")
    out = [head, ""]
    for z in grid.zones:
        i, j = cats[z]
        out.append(f"{z} {i} {j}")
    out.append("")
    pos = set(cats.values())
    for i in range(1, grid.n_rows + 1):
        out.append(" ".join("*" if (i, j) in pos else "." for j in range(1, grid.n_cols + 1)))
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Vérification (indépendante du solveur)
# --------------------------------------------------------------------------- #
def check_solution(grid: Grid, cats: dict[str, Cell]) -> list[str]:
    """Renvoie la liste des règles violées (liste vide <=> solution licite)."""
    errors = []
    if set(cats) != set(grid.zones):
        errors.append(f"régions sans chat ou inconnues : {sorted(set(grid.zones) ^ set(cats))}")
    pos = list(cats.items())
    for z, (i, j) in pos:
        if not (1 <= i <= grid.n_rows and 1 <= j <= grid.n_cols):
            errors.append(f"{z} : case ({i},{j}) hors grille")
        elif grid.zone_of((i, j)) != z:
            errors.append(f"{z} : la case ({i},{j}) appartient à {grid.zone_of((i, j))}")
    for a in range(len(pos)):
        for b in range(a + 1, len(pos)):
            (za, (ia, ja)), (zb, (ib, jb)) = pos[a], pos[b]
            if ia == ib:
                errors.append(f"{za},{zb} : même ligne {ia}")
            if ja == jb:
                errors.append(f"{za},{zb} : même colonne {ja}")
            if max(abs(ia - ib), abs(ja - jb)) <= 1:
                errors.append(f"{za},{zb} : chats adjacents")
    return errors


def cats_from_cells(grid: Grid, cells) -> dict[str, Cell]:
    """Ensemble de cases avec chat -> dictionnaire région -> case."""
    cats: dict[str, Cell] = {}
    for c in sorted(cells):
        z = grid.zone_of(c)
        if z in cats:
            raise GridError(f"deux chats dans la région {z}")
        cats[z] = c
    return cats
