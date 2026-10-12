import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from meowdoku.encode import encode  # noqa: E402
from meowdoku.generate import generate, other_solution  # noqa: E402
from meowdoku.grid import (cats_from_cells, check_solution, format_solution,  # noqa: E402
                           parse_grid_string, parse_solution_string, read_grid)
from solver import cdcl, dpll_h  # noqa: E402

FIG2 = {"A": (3, 2), "B": (2, 5), "C": (1, 3), "D": (5, 6), "E": (4, 4), "F": (6, 1)}


def test_figure1_solution():
    g = read_grid(os.path.join(ROOT, "data/grids/grille1.txt"))
    assert check_solution(g, FIG2) == []
    cnf, enc = encode(g)
    s, m = cdcl.solve(cnf.clauses, cnf.num_vars)
    assert s and cats_from_cells(g, enc.decode(m)) == FIG2      # solution unique
    assert other_solution(g, sorted(FIG2.values())) is None


def test_solution_roundtrip():
    g = read_grid(os.path.join(ROOT, "data/grids/grille1.txt"))
    g2, cats, stars = parse_solution_string(format_solution(g, FIG2))
    assert cats == FIG2 and g2.cells == g.cells
    assert sum(r.count("*") for r in stars) == 6


def test_checker_detects_violations():
    g = read_grid(os.path.join(ROOT, "data/grids/grille1.txt"))
    bad = dict(FIG2, E=(4, 3))      # (4,3) appartient à A
    assert check_solution(g, bad)


@pytest.mark.parametrize("n", [4, 5, 6, 8, 10, 13])
def test_generated_grids_are_solvable(n):
    for seed in range(3):
        g, sol = generate(n, seed=seed)
        cats = {g.zone_of(c): c for c in sol}
        assert check_solution(g, cats) == []
        assert sorted(len(c) for c in g.regions().values())[0] >= 1
        cnf, enc = encode(g, redundant=(seed % 2 == 0), amo="seq" if seed == 2 else "pairwise")
        s, m = cdcl.solve(cnf.clauses, cnf.num_vars)
        assert s and check_solution(g, cats_from_cells(g, enc.decode(m))) == []


def test_unique_generator():
    g, sol = generate(7, seed=3, unique=True)
    assert other_solution(g, sol) is None


def test_non_square():
    g, sol = generate(6, 8, 5, seed=1)
    cnf, enc = encode(g)
    s, m, _ = dpll_h.solve(cnf.clauses, cnf.num_vars, "H4d")
    assert s and check_solution(g, cats_from_cells(g, enc.decode(m))) == []


def test_comment_vs_zone_named_c():
    text = "c commentaire\nGRID 2 2\nZONES c d\nc d\nc c\n"
    g = parse_grid_string(text)
    assert g.cells == [["c", "d"], ["c", "c"]]
