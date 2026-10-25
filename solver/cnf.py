"""Question 2.1 -- Lecture / écriture de fichiers DIMACS CNF.

Représentation retenue pour une formule CNF :

* une variable est un entier strictement positif (1..num_vars) ;
* un littéral est un entier non nul : ``k`` pour x_k et ``-k`` pour ¬x_k
  (exactement la convention DIMACS) ;
* une clause est une séquence de littéraux (``list[int]`` en lecture,
  ``frozenset[int]`` dans le DPLL « naïf » de dpll.py) ;
* une formule est la classe :class:`CNF` (nombre de variables + liste de clauses).

Ce choix colle au format DIMACS : la traduction fichier -> structure est
quasiment directe, et les opérations « négation » (``-l``) et
« variable » (``abs(l)``) sont en O(1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


class DimacsError(ValueError):
    """Fichier DIMACS mal formé."""


@dataclass
class CNF:
    num_vars: int
    clauses: list[list[int]] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    @property
    def num_clauses(self) -> int:
        return len(self.clauses)

    def variables(self) -> set[int]:
        return {abs(l) for c in self.clauses for l in c}

    def __str__(self) -> str:  # pragma: no cover - confort d'affichage
        return " ∧ ".join("(" + " ∨ ".join(_lit_str(l) for l in c) + ")" for c in self.clauses)


def _lit_str(l: int) -> str:
    return f"x{l}" if l > 0 else f"¬x{-l}"


# --------------------------------------------------------------------------- #
# Lecture
# --------------------------------------------------------------------------- #
def parse_dimacs_string(text: str, strict: bool = False) -> CNF:
    """Analyse un texte DIMACS CNF.

    Tolérances (rencontrées dans les fichiers SATLIB) :
      * une clause peut s'étendre sur plusieurs lignes (seul le 0 la termine) ;
      * une ligne ``%`` marque la fin des données (le reste est ignoré) ;
      * espaces multiples / en début de ligne.
    Si ``strict`` est vrai, une incohérence avec l'en-tête lève DimacsError ;
    sinon le nombre de variables est porté au plus grand indice rencontré.
    """
    num_vars = num_clauses = None
    comments: list[str] = []
    body: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        head = line[0]
        if head == "c":
            comments.append(line[1:].strip())
            continue
        if head == "%":
            break
        if head == "p":
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf":
                raise DimacsError(f"en-tête invalide : {line!r}")
            if num_vars is not None:
                raise DimacsError("en-tête 'p cnf' dupliqué")
            num_vars, num_clauses = int(parts[2]), int(parts[3])
            continue
        if num_vars is None:
            raise DimacsError("clause rencontrée avant l'en-tête 'p cnf'")
        body.append(line)

    if num_vars is None:
        raise DimacsError("en-tête 'p cnf <vars> <clauses>' manquant")

    try:
        ints = list(map(int, " ".join(body).split()))
    except ValueError as e:
        raise DimacsError(f"littéral non entier : {e}") from None

    clauses: list[list[int]] = []
    cur: list[int] = []
    max_var = 0
    for x in ints:
        if x == 0:
            clauses.append(cur)
            cur = []
        else:
            cur.append(x)
            if x > max_var or -x > max_var:
                max_var = abs(x)
    if cur:  # dernière clause sans 0 final : tolérée hors mode strict
        if strict:
            raise DimacsError("dernière clause non terminée par 0")
        clauses.append(cur)

    if strict:
        if max_var > num_vars:
            raise DimacsError(f"variable {max_var} > {num_vars} déclarées")
        if len(clauses) != num_clauses:
            raise DimacsError(f"{len(clauses)} clauses lues, {num_clauses} déclarées")
    elif len(clauses) != num_clauses:
        # Certains fichiers (ex. SATLIB dubois100) omettent le 0 final de
        # nombreuses lignes : la lecture « jusqu'au 0 » fusionne alors des
        # clauses et change la formule. Si la lecture « une ligne = une
        # clause » (règle de l'énoncé) est cohérente avec l'en-tête, on la retient.
        by_line = _clauses_by_line(body)
        if by_line is not None and len(by_line) == num_clauses:
            clauses = by_line
    return CNF(max(num_vars, max_var), clauses, comments)


def _clauses_by_line(body: list[str]) -> list[list[int]] | None:
    """Une clause par ligne (0 final facultatif) ; None si une ligne contient
    un 0 ailleurs qu'en dernière position."""
    clauses = []
    for line in body:
        lits = list(map(int, line.split()))
        if lits and lits[-1] == 0:
            lits.pop()
        if 0 in lits:
            return None
        clauses.append(lits)
    return clauses


def parse_dimacs(path: str, strict: bool = False) -> CNF:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_dimacs_string(f.read(), strict=strict)


# --------------------------------------------------------------------------- #
# Écriture
# --------------------------------------------------------------------------- #
def to_dimacs_string(cnf: CNF, comments: Iterable[str] = ()) -> str:
    out = [f"c {c}" if c else "c" for c in list(comments) or cnf.comments]
    out.append(f"p cnf {cnf.num_vars} {len(cnf.clauses)}")
    out.extend(" ".join(map(str, c)) + " 0" for c in cnf.clauses)
    return "\n".join(out) + "\n"


def write_dimacs(cnf: CNF, path: str, comments: Iterable[str] = ()) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_dimacs_string(cnf, comments))


# --------------------------------------------------------------------------- #
# Valuations
# --------------------------------------------------------------------------- #
def complete_model(valuation: Mapping[int, bool], num_vars: int) -> dict[int, bool]:
    """Complète une valuation partielle (les variables disparues de la formule
    au cours de DPLL peuvent prendre n'importe quelle valeur : on choisit False)."""
    return {v: bool(valuation.get(v, False)) for v in range(1, num_vars + 1)}


def check_model(clauses: Iterable[Iterable[int]], model: Mapping[int, bool]) -> bool:
    """Vrai ssi chaque clause contient au moins un littéral vrai sous ``model``."""
    for c in clauses:
        for l in c:
            if model.get(abs(l), False) == (l > 0):
                break
        else:
            return False
    return True


def model_to_dimacs_line(model: Mapping[int, bool], num_vars: int) -> str:
    return "v " + " ".join(str(v if model.get(v, False) else -v) for v in range(1, num_vars + 1)) + " 0"
