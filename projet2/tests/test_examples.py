"""The four models of the statement (table 1), the command line, and the
Meowdoku models (question 6) checked by independent verifiers."""

import random
import subprocess
import sys
from pathlib import Path

import pytest

from cspc.compiler import compile_text
from cspc.solving import solve
from meowdoku.generate import generate
from meowdoku.grid import Grid, parse_grid_string
from tools.brute_force import brute_force
from tools.meowdoku_models import MODEL_NAMES
from tools.solve_grid import run_model

ROOT = Path(__file__).resolve().parent.parent
EXEMPLES = ROOT / "exemples"


def solve_file(path, mode="optimized", amo="pairwise"):
    enc = compile_text(Path(path).read_text(), amo).encoding
    sat, values = solve(enc, mode)
    return sat, dict(enc.decode(values)) if sat else None


# ---- independent verifiers -----------------------------------------------

def check_sudoku(sol):
    g = [[int(sol[f"grid[{i}][{j}]"]) for j in range(1, 10)] for i in range(1, 10)]
    groups = [row for row in g] + [list(col) for col in zip(*g)] + \
             [[g[3 * a + i][3 * b + j] for i in range(3) for j in range(3)] for a in range(3) for b in range(3)]
    assert all(sorted(grp) == list(range(1, 10)) for grp in groups)
    given = [[5, 3, 0, 0, 7, 0, 0, 0, 0], [6, 0, 0, 1, 9, 5, 0, 0, 0], [0, 9, 8, 0, 0, 0, 0, 6, 0],
             [8, 0, 0, 0, 6, 0, 0, 0, 3], [4, 0, 0, 8, 0, 3, 0, 0, 1], [7, 0, 0, 0, 2, 0, 0, 0, 6],
             [0, 6, 0, 0, 0, 0, 2, 8, 0], [0, 0, 0, 4, 1, 9, 0, 0, 5], [0, 0, 0, 0, 8, 0, 0, 7, 9]]
    assert all(given[i][j] in (0, g[i][j]) for i in range(9) for j in range(9))


def check_queens(sol):
    q = [int(sol[f"queen[{i}]"]) for i in range(1, 9)]
    assert sorted(q) == list(range(1, 9))
    assert all(abs(q[i] - q[j]) != j - i for i in range(8) for j in range(i + 1, 8))


def check_coloring(sol):
    edges = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 1), (6, 8), (8, 10), (10, 7), (7, 9), (9, 6),
             (1, 6), (2, 7), (3, 8), (4, 9), (5, 10)]
    assert all(sol[f"color[{u}]"] != sol[f"color[{v}]"] for u, v in edges)
    assert sol["color[1]"] == "Red" and sol["color[2]"] == "Green"
    assert len(sol) == 10


@pytest.mark.parametrize("amo", ["pairwise", "sinz"])
@pytest.mark.parametrize("mode", ["optimized", "dpll"])
def test_examples_of_the_statement(mode, amo):
    sat, _ = solve_file(EXEMPLES / "pigeonhole.csp", mode, amo)
    assert not sat
    for name, check in [("coloring", check_coloring), ("queens", check_queens)]:
        sat, sol = solve_file(EXEMPLES / f"{name}.csp", mode, amo)
        assert sat
        check(sol)


@pytest.mark.parametrize("amo", ["pairwise", "sinz"])
def test_sudoku(amo):
    sat, sol = solve_file(EXEMPLES / "sudoku.csp", amo=amo)
    assert sat
    check_sudoku(sol)


def test_pigeonhole_sizes():
    for pigeons, holes in [(1, 1), (2, 3), (3, 3), (4, 3), (5, 4)]:
        text = (f"const P = {pigeons}; const H = {holes}; array hole[P] : 1..H;"
                "constraint allDifferent(hole[*]);")
        sat, _ = solve(compile_text(text).encoding)
        assert sat == (pigeons <= holes)


def test_propositional_fragment():
    # (precedence.csp is unsatisfiable: `not a and b` contradicts `a and b and c`)
    for name, expected in [("subject", True), ("precedence", False), ("pigeonhole", False)]:
        text = (ROOT / "examples" / f"{name}.csp").read_text()
        sat, _ = solve(compile_text(text).encoding)
        assert sat == expected, name


# ---- command line --------------------------------------------------------

def csp(*args):
    return subprocess.run([sys.executable, str(ROOT / "csp.py"), *map(str, args)],
                          capture_output=True, text=True, cwd=ROOT)


def test_cli_solve():
    out = csp(EXEMPLES / "coloring.csp", "--solve")
    assert out.returncode == 0
    lines = out.stdout.splitlines()
    assert lines[0] == "s SATISFIABLE" and "color[1] = Red" in lines and len(lines) == 11
    out = csp(EXEMPLES / "pigeonhole.csp", "--solve")
    assert out.stdout.strip() == "s UNSATISFIABLE"


def test_cli_dimacs(tmp_path):
    out = csp(EXEMPLES / "pigeonhole.csp")
    assert "p cnf 12 34" in out.stdout and "c var 1 hole[1]=1" in out.stdout
    csp(EXEMPLES / "pigeonhole.csp", "--dimacs", tmp_path / "f.cnf")
    assert (tmp_path / "f.cnf").read_text() == out.stdout


def test_cli_errors(tmp_path):
    bad = tmp_path / "bad.csp"
    bad.write_text("var x : 1..3;\nconstraint x + 1 = 2;\n")
    out = csp(bad, "--solve")
    assert out.returncode == 1 and out.stdout == ""
    assert out.stderr.startswith(f"{bad}: line 2, column 12: arithmetic is only allowed on known values")
    assert "Traceback" not in out.stderr
    bad.write_text("var x : 1..3;\nconstraint x = ;\n")
    out = csp(bad)
    assert out.returncode == 1 and "line 2, column 16: syntax error" in out.stderr
    assert csp(tmp_path / "missing.csp").returncode == 2


def test_cli_warns_on_false_constraint(tmp_path):
    model = tmp_path / "m.csp"
    model.write_text("var x : 1..3;\nforall i in 1..2 { constraint i = 2 -> x < 1 and 1 = 2; }\n")
    out = csp(model, "--solve")
    assert out.stdout.strip() == "s UNSATISFIABLE"
    assert "always false" in out.stderr and "i=2" in out.stderr


def test_cli_ast_and_ground():
    assert csp(EXEMPLES / "pigeonhole.csp", "--ast").stdout.startswith("Program\n  Const P = 4")
    assert csp(EXEMPLES / "pigeonhole.csp", "--ground").stdout == "allDifferent(hole[1], hole[2], hole[3], hole[4])\n"


# ---- Meowdoku (question 6) -----------------------------------------------

FIGURE_1 = parse_grid_string("""GRID 6 6
ZONES A B C D E F
A B C B B D
A B B B B D
A A B D D D
A A A E D D
A A A A D D
F A D D D D
""")


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_figure_1_with_each_model(name):
    run = run_model(FIGURE_1, name)
    assert run.satisfiable and not run.errors
    assert run.cats == {"A": (3, 2), "B": (2, 5), "C": (1, 3), "D": (5, 6), "E": (4, 4), "F": (6, 1)}


def planted(n, seed):
    grid, _ = generate(n, seed=seed)
    return grid


def unsat_grid():
    """A grid with a single cell in the regions A, B: they are on neighbouring cells."""
    return parse_grid_string("GRID 3 3\nZONES A B C\nA B C\nC C C\nC C C\n")


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_models_agree_on_generated_grids(name):
    for n, seed in [(5, 1), (6, 2), (7, 3)]:
        run = run_model(planted(n, seed), name)
        assert run.satisfiable and not run.errors, (name, n)
    run = run_model(unsat_grid(), name)
    assert not run.satisfiable


def random_grid(rng):
    """A random partition of a small N x M grid into K regions (not necessarily connected)."""
    n, m = rng.randint(1, 5), rng.randint(1, 5)
    k = rng.randint(1, min(n * m, 5))
    owner = [rng.randrange(k) for _ in range(n * m)]
    for z, position in enumerate(rng.sample(range(n * m), k)):   # every region has a cell
        owner[position] = z
    zones = [chr(65 + z) for z in range(k)]
    return Grid(n, m, zones, [[zones[owner[i * m + j]] for j in range(m)] for i in range(n)])


def test_general_model_against_exhaustive_search():
    rng = random.Random(5)
    seen = {True: 0, False: 0}
    for _ in range(80):
        grid = random_grid(rng)
        expected = brute_force(grid)
        run = run_model(grid, "general")
        assert run.satisfiable == (expected is not None), grid
        assert not run.errors
        seen[run.satisfiable] += 1
    assert seen[True] >= 5 and seen[False] >= 5    # the sample contains both answers


def test_redundant_rule_does_not_change_the_answers():
    rng = random.Random(7)
    for _ in range(25):
        n = rng.randint(4, 6)
        grid, _ = generate(n, seed=rng.randrange(1000), planted=rng.random() < 0.5)
        answers = {name: run_model(grid, name).satisfiable for name in ("cells", "cells_redundant", "general")}
        assert len(set(answers.values())) == 1, (grid, answers)
