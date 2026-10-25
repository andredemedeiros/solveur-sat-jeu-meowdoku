#!/usr/bin/env python3
"""Mesures complémentaires citées dans le rapport (hors campagnes principales).

Chaque ligne indique la question du rapport concernée. Les mesures de temps
sont faites ici ; les autres chiffres sont relus dans les résultats déjà
produits (results/validation, results/benchmark, results/competition).

    python experiments/extra_measures.py > results/extra_measures.txt
Durée : quelques minutes (jusqu'à 15 min si les essais d'unicité en
14 × 14 atteignent leur limite de 300 s). Nécessite pycosat (PicoSAT).
"""
import csv
import glob
import math
import multiprocessing as mp
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du dépôt
sys.path.insert(0, ROOT)

from meowdoku.encode import encode  # noqa: E402
from meowdoku.generate import generate, other_solution  # noqa: E402
from meowdoku.grid import read_grid  # noqa: E402
from solver import cdcl  # noqa: E402
from solver.cnf import parse_dimacs  # noqa: E402


def path(*p):
    return os.path.join(ROOT, *p)


def gmean(xs):
    xs = list(xs)
    return math.exp(sum(map(math.log, xs)) / len(xs))


def rows(*p):
    with open(path(*p), encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------------- #
def q1():
    print("## Q1 -- modélisation et générateur")
    g = read_grid(path("data", "examples", "grille1.txt"))
    cnf, enc = encode(g)
    N, M = g.n_rows, g.n_cols
    raw = (g.K + sum(len(c) * (len(c) - 1) // 2 for c in g.regions().values())
           + N * M * (M - 1) // 2 + M * N * (N - 1) // 2 + 2 * (N - 1) * (M - 1) + N + M)
    print(f"figure 1 : {cnf.num_clauses} clauses ({raw} sans dédoublonnage)")
    sol = sorted(enc.decode(cdcl.solve(cnf.clauses, cnf.num_vars)[1]))
    print("figure 1 : solution unique :", other_solution(g, sol) is None)

    grid, _ = generate(50, seed=0)
    cnf, _ = encode(grid)
    t = time.process_time()
    sat, _ = cdcl.solve(cnf.clauses, cnf.num_vars)
    print(f"grille 50 x 50 (graine 0) : {cnf.num_clauses} clauses, SAT={sat}, "
          f"CDCL {time.process_time() - t:.2f} s de CPU")

    for n in (8, 10, 12):
        ts = []
        for seed in range(3):
            t = time.perf_counter()
            generate(n, seed=seed, unique=True)
            ts.append(time.perf_counter() - t)
        print(f"générateur --unique {n} x {n} (graines 0-2) : " + ", ".join(f"{x:.1f}" for x in ts) + " s")
    for seed in range(3):            # chaque essai est limité à 300 s
        p = mp.Process(target=generate, args=(14,), kwargs={"seed": seed, "unique": True})
        t = time.perf_counter()
        p.start()
        p.join(300)
        if p.is_alive():
            p.terminate()
            p.join()
            print(f"générateur --unique 14 x 14 (graine {seed}) : non terminé en 300 s")
        else:
            print(f"générateur --unique 14 x 14 (graine {seed}) : {time.perf_counter() - t:.1f} s")

    st = [parse_dimacs(f).comments for f in glob.glob(path("data", "generated", "cnf", "meow_rnd", "*.cnf"))]
    unsat = sum("status UNSAT" in c for c in st)
    print(f"grilles à régions aléatoires : {unsat} UNSAT sur {len(st)}")


def q2():
    print("\n## Q2 -- lecture DIMACS, validation, algorithmes 1 et 2")
    late = []
    for f in sorted(glob.glob(path("data", "public-instances", "instances", "*.cnf"))):
        with open(f, encoding="utf-8") as fh:
            body = [l.strip() for l in fh if l.strip() and l.strip()[0] not in "cp%"]
        if any(l.split()[-1] != "0" for l in body):
            late.append(os.path.basename(f))
    print("instances publiques dont des clauses ne finissent pas par 0 sur leur ligne :", ", ".join(late))
    norm = lambda c: sorted(sorted(x) for x in c.clauses)
    a = parse_dimacs(path("data", "public-instances", "instances", "public-03.cnf"))
    b = parse_dimacs(path("data", "satlib", "dubois", "dubois21.cnf"))
    print("public-03 identique à dubois21 :", (a.num_vars, norm(a)) == (b.num_vars, norm(b)))

    v = rows("results", "validation", "validation.csv")
    by = {(r["instance"], r["solver"]): r for r in v}
    pairs = [(by[(i, "alg1")], by[(i, "alg2")]) for i in {r["instance"] for r in v}]
    same_to = all((x["status"] == "TIMEOUT") == (y["status"] == "TIMEOUT") for x, y in pairs)
    ok = [(float(x["cpu"]), float(y["cpu"])) for x, y in pairs
          if "TIMEOUT" not in (x["status"], y["status"]) and float(x["cpu"]) > 0.01]
    print(f"algorithme 1 / algorithme 2 : rapport géométrique {gmean(p / q for p, q in ok):.2f} "
          f"sur {len(ok)} instances (> 10 ms), mêmes délais dépassés : {same_to}")


def q5():
    print("\n## Q5 -- Meowdoku (results/benchmark/bench.csv, limite 20 s, PAR-2 = 40 s)")
    b = rows("results", "benchmark", "bench.csv")
    par2 = lambda r: float(r["cpu"]) if r["status"] != "TIMEOUT" else 40.0
    size = lambda r: int(os.path.basename(r["instance"]).split("_")[1].split("x")[0])
    solvers = sorted({r["solver"] for r in b})
    for label, keep in (("grilles plantées N >= 16 : % résolues",
                         lambda r: r["family"] == "meow_sat" and size(r) >= 16),
                        ("grilles à régions aléatoires : % résolues", lambda r: r["family"] == "meow_rnd")):
        print(label)
        for s in solvers:
            rs = [r for r in b if r["solver"] == s and keep(r)]
            print(f"  {s:10s} {100 * sum(r['status'] != 'TIMEOUT' for r in rs) / len(rs):5.0f}")
    print("grilles plantées 24 x 24 : PAR-2 (moyenne géométrique, s)")
    for s in solvers:
        rs = [r for r in b if r["solver"] == s and r["family"] == "meow_sat" and size(r) == 24]
        print(f"  {s:10s} {gmean(map(par2, rs)):6.2f}")


def q6():
    print("\n## Q6 -- compétition, mode optimized (results/competition/competition_optimized.csv)")
    c = rows("results", "competition", "competition_optimized.csv")
    ok = [r for r in c if r["ok"] == "True"]
    times = [float(r["time"]) for r in ok]      # (des noms de fichiers se répètent entre dossiers)
    print(f"résolues {len(ok)} / {len(c)} ; < 0,5 s : {sum(x < 0.5 for x in times)} ; "
          f"< 2 s : {sum(x < 2 for x in times)} ; médiane {statistics.median(times):.2f} s")
    slow = sorted((float(r["time"]), r["instance"]) for r in ok if float(r["time"]) > 2)
    print("> 2 s :", ", ".join(f"{os.path.basename(i)} {x:.1f} s" for x, i in slow))
    t = {r["instance"]: float(r["time"]) for r in ok}
    print("formules triviales :", ", ".join(f"{os.path.basename(k)} {t[k]:.2f} s" for k in (
        "data/examples/lampes.cnf", "data/public-instances/instances/smoke_01_sat.cnf",
        "data/public-instances/instances/unit_01_sat.cnf")))


def picosat():
    print("\n## Limites -- CDCL (Python) contre PicoSAT (C, via pycosat, conversion comprise)")
    import pycosat
    files = (sorted(glob.glob(path("data", "satlib", "uuf75-325", "*.cnf")))[:10]
             + sorted(glob.glob(path("data", "satlib", "uf100-430", "*.cnf")))[:10]
             + sorted(glob.glob(path("data", "satlib", "flat50-115", "*.cnf")))[:10]
             + sorted(glob.glob(path("data", "generated", "cnf", "meow_sat", "meow_2*.cnf")))
             + sorted(glob.glob(path("data", "public-instances", "instances", "public-1[129].cnf"))))
    ratios = []
    for f in files:
        cnf = parse_dimacs(f)
        t = time.process_time()
        cdcl.solve(cnf.clauses, cnf.num_vars)
        tc = time.process_time() - t
        t = time.process_time()
        for _ in range(5):
            pycosat.solve(cnf.clauses)
        tp = (time.process_time() - t) / 5
        ratios.append(tc / max(tp, 1e-5))
    print(f"{len(files)} instances : CDCL / PicoSAT = {gmean(ratios):.0f} (moyenne géométrique), "
          f"de {min(ratios):.0f} à {max(ratios):.0f}")


if __name__ == "__main__":
    print(f"# Mesures complémentaires (Python {sys.version.split()[0]})\n")
    for step in (q1, q2, q5, q6, picosat):
        step()
        sys.stdout.flush()
