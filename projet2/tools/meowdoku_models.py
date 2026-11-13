"""Meowdoku as a constraint model (question 6).

A model is the *data* of a grid (sizes, regions), which changes from one
grid to the next, followed by the *rules* of the game, written once for all
in models/meowdoku/<name>.csp.

    grid_to_data(grid)       Q6.1: a part I grid file  ->  declarations
    build_model(grid, name)  data + rules
    cats_from_values(...)    solution of the model  ->  cat of each region
"""

from __future__ import annotations

import re
from pathlib import Path

from meowdoku.grid import Cell, Grid, cats_from_cells

MODELS_DIR = Path(__file__).resolve().parent.parent / "models" / "meowdoku"
MODEL_NAMES = ("positions", "cells", "cells_redundant", "general")

# names used by the rules, and the keywords: a region must not take them
RESERVED = {"const", "enum", "var", "array", "bool", "constraint", "forall", "in", "not", "and", "or",
            "abs", "N", "M", "K", "Zone", "region", "row", "col", "cat", "z", "z1", "z2",
            "i", "j", "k", "l", "i1", "j1", "i2", "j2", "atLeastOne", "atMostOne", "exactlyOne",
            "allDifferent"}
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")


def zone_identifiers(zones: list[str]) -> dict[str, str]:
    """Name of each region in the model: itself, unless it is not a valid
    identifier or collides with a keyword or a name of the rules (then `Z_name`)."""
    names = {}
    for z in zones:
        ok = IDENTIFIER.match(z) and z not in RESERVED
        names[z] = z if ok else "Z_" + re.sub(r"\W", "_", z)
    if len(set(names.values())) != len(names):
        names = {z: f"Z{k}" for k, z in enumerate(zones, start=1)}
    return names


def grid_to_data(grid: Grid) -> str:
    """The declarations of a grid: sizes, enum of regions, region of each cell."""
    ident = zone_identifiers(grid.zones)
    rows = ",\n".join("    [" + ", ".join(ident[z] for z in row) + "]" for row in grid.cells)
    return (f"const N = {grid.n_rows};   // rows\n"
            f"const M = {grid.n_cols};   // columns\n"
            f"const K = {grid.K};   // regions\n"
            f"enum Zone = {{ {', '.join(ident[z] for z in grid.zones)} }};\n"
            f"const region[N][M] = [\n{rows}\n];\n")


def rules(name: str) -> str:
    if name not in MODEL_NAMES:
        raise ValueError(f"unknown model {name!r}; choose from {', '.join(MODEL_NAMES)}")
    return (MODELS_DIR / f"{name}.csp").read_text(encoding="utf-8")


def build_model(grid: Grid, name: str) -> str:
    """The complete text of the model `name` for `grid`."""
    if name in ("positions", "cells", "cells_redundant") and not grid.n_rows == grid.n_cols == grid.K:
        raise ValueError(f"model {name!r} needs N = M = K; use 'general' "
                         f"(grid {grid.n_rows}x{grid.n_cols} with {grid.K} regions)")
    return f"// Meowdoku, model '{name}'.\n\n{grid_to_data(grid)}\n{rules(name)}"


_CELL = re.compile(r"cat\[(\d+)\]\[(\d+)\]")
_POS = re.compile(r"(row|col)\[(\w+)\]")


def cats_from_values(grid: Grid, values: list[tuple[str, str]], name: str) -> dict[str, Cell]:
    """Cat of each region (by its original name) from the (name, value) pairs of a solution."""
    if name == "positions":
        ident = zone_identifiers(grid.zones)
        back = {v: k for k, v in ident.items()}
        rows, cols = {}, {}
        for var, value in values:
            kind, zone = _POS.fullmatch(var).groups()
            (rows if kind == "row" else cols)[back[zone]] = int(value)
        return {z: (rows[z], cols[z]) for z in grid.zones}
    cells = [(int(m[1]), int(m[2])) for var, value in values
             if value == "true" and (m := _CELL.fullmatch(var))]
    return cats_from_cells(grid, cells)
