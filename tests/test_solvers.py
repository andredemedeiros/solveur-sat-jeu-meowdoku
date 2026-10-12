"""Tests unitaires : python -m pytest -q tests"""
import itertools
import os
import random
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from solver import cdcl, dpll, dpll_h, heuristics as H  # noqa: E402
from solver.cnf import check_model, parse_dimacs_string, to_dimacs_string  # noqa: E402

LAMPES = """c --- Exemple : Enigme des 3 lampes ---
c Variables : 1 = L1, 2 = L2, 3 = L3
p cnf 3 4
1 2 3 0
-1 -2 0
-2 -3 0
2 3 0
"""
EXAMPLE = [[1, 2, -4], [2, 3], [1, -2, 4, -5]]   # formule d'exemple de la Q4


def brute_force(clauses, n):
    for bits in itertools.product([False, True], repeat=n):
        m = {i + 1: b for i, b in enumerate(bits)}
        if check_model(clauses, m):
            return True
    return False


def random_cnf(rng, n, m, k=3):
    return [[v if rng.random() < .5 else -v for v in rng.sample(range(1, n + 1), min(k, n))] for _ in range(m)]


def test_parse_lampes():
    cnf = parse_dimacs_string(LAMPES)
    assert cnf.num_vars == 3 and cnf.clauses == [[1, 2, 3], [-1, -2], [-2, -3], [2, 3]]
    assert parse_dimacs_string(to_dimacs_string(cnf)).clauses == cnf.clauses


def test_parse_satlib_quirks():
    cnf = parse_dimacs_string("c x\np cnf 3 2\n 1 -2\n 3 0\n-1 0\n%\n0\n")
    assert cnf.clauses == [[1, -2, 3], [-1]]


def test_assign():
    F = dpll.make_formula(EXAMPLE)
    assert set(dpll.assign(F, 2)) == {frozenset([1, 4, -5])}
    assert set(dpll.assign(F, -2)) == {frozenset([1, -4]), frozenset([3])}


def test_heuristic_examples():
    F = dpll.make_formula(EXAMPLE)
    lits = set().union(*F)
    s = H.jw_scores(F)
    assert abs(s[2] + s.get(-2, 0) - 7 / 16) < 1e-12          # exemple de l'énoncé
    assert H.VJWDynamic().choose(F, lits) == (2, True)
    assert H.VPPMDynamic().choose(F, lits) == (2, True)         # #(x2)=3 maximal
    assert H.LPDynamic().choose(F, lits) == (1, True)           # occ(x1)=occ(x2)=2 -> plus petit indice
    assert H.VFCMDynamic().choose(F, lits) == (2, True)         # k=2 : clause (x2 ∨ x3)
    assert H.FirstFree().choose(F, lits) == (1, True)


@pytest.mark.parametrize("seed", range(40))
def test_all_solvers_vs_brute_force(seed):
    rng = random.Random(seed)
    n = rng.randint(3, 10)
    clauses = random_cnf(rng, n, rng.randint(1, 6 * n), k=rng.randint(1, 4))
    expected = brute_force(clauses, n)
    assert dpll.solve_sat(clauses, seed=seed) == expected
    s, m = dpll.solve(clauses, n, seed=seed)
    assert s == expected and (not s or check_model(clauses, m))
    for code in H.ALL_CODES:
        s, m, _ = dpll_h.solve(clauses, n, code, seed=seed)
        assert s == expected and (not s or check_model(clauses, m)), code
    s, m = cdcl.solve(clauses, n)
    assert s == expected and (not s or check_model(clauses, m))


def test_empty_cases():
    assert dpll.solve([], 2)[0] is True
    assert dpll.solve([[]], 2)[0] is False
    assert cdcl.solve([], 2)[0] is True
    assert cdcl.solve([[1], [-1]], 1)[0] is False


def test_sat_cli(tmp_path):
    f = tmp_path / "l.cnf"
    f.write_text(LAMPES)
    for mode in ("dpll", "optimized"):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "sat.py"), str(f), "--mode", mode,
                              "--output-model"], capture_output=True, text=True).stdout.split("\n")
        assert out[0] == "s SATISFIABLE"
        lits = list(map(int, out[1].split()[1:]))
        assert lits[-1] == 0 and check_model([[1, 2, 3], [-1, -2], [-2, -3], [2, 3]],
                                             {abs(l): l > 0 for l in lits[:-1]})
    f.write_text("p cnf 1 2\n1 0\n-1 0\n")
    out = subprocess.run([sys.executable, os.path.join(ROOT, "sat.py"), str(f), "--output-model"],
                         capture_output=True, text=True).stdout
    assert out == "s UNSATISFIABLE\n"
