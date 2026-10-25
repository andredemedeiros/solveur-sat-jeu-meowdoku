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


def test_parse_missing_terminators():
    # dubois100 (SATLIB) : 0 final absent sur certaines lignes, une clause par ligne
    cnf = parse_dimacs_string("p cnf 2 4\n1 2\n-1 2 0\n1 -2\n-1 -2 0\n")
    assert cnf.clauses == [[1, 2], [-1, 2], [1, -2], [-1, -2]]
    assert cdcl.solve(cnf.clauses, 2)[0] is False


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
    for choice in H.MRV.CHOICES:     # variantes de H9 (experiments/h9_variants.py)
        s, m = dpll_h.DPLLH(H.MRV(choice)).solve(clauses, n)
        assert s == expected and (not s or check_model(clauses, m)), choice
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


@pytest.mark.parametrize("name", ["satlib/uf50-218/uf50-01.cnf", "satlib/uuf50-218/uuf50-01.cnf",
                                  "satlib/uuf75-325/uuf75-01.cnf", "generated/cnf/meow_nored/meow_16x16_0.cnf"])
def test_cdcl_resume_after_timeout(name):
    # recherche interrompue à chaque décision (délai nul) puis reprise :
    # même statut que sans interruption, modèle valide
    from solver.cnf import parse_dimacs
    from solver.runner import expected_status
    path = os.path.join(ROOT, "data", name)
    cnf = parse_dimacs(path)
    s = cdcl.CDCL(cnf.num_vars, cnf.clauses)
    s.CHECK_MASK = 0
    interruptions = 0
    while True:
        try:
            sat = s.solve(timeout=0)
            break
        except TimeoutError:
            interruptions += 1
    assert interruptions > 0
    assert ("SAT" if sat else "UNSAT") == expected_status(path, cnf)
    assert not sat or check_model(cnf.clauses, s.model())


@pytest.mark.parametrize("seed", range(5))
def test_portfolio(seed):
    from solver import portfolio
    rng = random.Random(200 + seed)
    n = rng.randint(5, 12)
    clauses = random_cnf(rng, n, rng.randint(n, 6 * n))
    sat, m = portfolio.solve(clauses, n, delay=0)   # processus DPLL lancé d'emblée
    assert sat == brute_force(clauses, n)
    assert not sat or check_model(clauses, m)


def test_model_line_without_variables():
    from solver.cnf import model_to_dimacs_line
    assert model_to_dimacs_line({}, 0) == "v 0"
    assert model_to_dimacs_line({1: True, 2: False}, 2) == "v 1 -2 0"


PUBLIC = os.path.join(ROOT, "data", "public-instances", "instances")


@pytest.mark.skipif(not os.path.isdir(PUBLIC), reason="instances publiques absentes")
def test_public_small_instances():
    # tests d'interface et cas limites fournis par les enseignants (expected.json)
    from solver.cnf import parse_dimacs
    from solver.runner import expected_status
    names = [f for f in sorted(os.listdir(PUBLIC)) if not f.startswith("public-")]
    assert len(names) == 11
    for name in names:
        path = os.path.join(PUBLIC, name)
        exp = expected_status(path)
        assert exp == ("UNSAT" if "unsat" in name else "SAT")
        for mode in ("dpll", "optimized"):
            out = subprocess.run([sys.executable, os.path.join(ROOT, "sat.py"), path, "--mode", mode,
                                  "--output-model"], capture_output=True, text=True).stdout
            if exp == "UNSAT":
                assert out == "s UNSATISFIABLE\n", (name, mode)
            else:
                first, v, end = out.split("\n")
                assert first == "s SATISFIABLE" and end == "" and v.startswith("v ") and v.endswith(" 0")
                lits = list(map(int, v.split()[1:-1]))
                assert check_model(parse_dimacs(path).clauses, {abs(l): l > 0 for l in lits}), (name, mode)


def _processes_running(fragment):
    pids = []
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if cmd.startswith(sys.executable) and fragment in cmd:
                pids.append(int(pid))
    return pids


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="surveillance du parent : Linux")
def test_portfolio_helper_dies_with_parent():
    # comme l'infrastructure de compétition : sat.py tué (SIGKILL) à la limite
    # de temps, après le lancement du DPLL auxiliaire (2 s) -- aucun processus
    # ne doit survivre
    import time
    hole10 = os.path.join(ROOT, "data", "satlib", "pigeon-hole", "hole10.cnf")
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run([sys.executable, os.path.join(ROOT, "sat.py"), hole10], timeout=3.5, capture_output=True)
    for _ in range(30):
        if not _processes_running("hole10.cnf"):
            break
        time.sleep(0.1)
    left = _processes_running("hole10.cnf")
    for pid in left:
        os.kill(pid, 9)
    assert not left
