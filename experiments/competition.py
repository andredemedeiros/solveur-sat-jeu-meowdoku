#!/usr/bin/env python3
"""Question 6 -- Simulation de la compétition : exécute ``python sat.py``
(sous-processus, comme l'infrastructure officielle) sur un ensemble
d'instances, vérifie le format de sortie, le statut et le modèle, puis
calcule le classement (nb d'instances correctement résolues, temps total).

    python experiments/competition.py [--mode optimized|dpll] [--timeout 60] [--jobs 4]
                                      [--csv out.csv] [dossiers/fichiers ...]

Statut attendu (solver.runner.expected_status) : ``expected.json`` du dossier
de l'instance ou de son parent (instances publiques des enseignants), sinon
commentaire « c status » de nos instances, sinon nom de fichier SATLIB.
Comme dans le règlement, une instance est correctement résolue si le statut
est le statut attendu et, pour SAT, si le modèle satisfait toutes les
clauses. Une instance sans statut attendu connu est signalée « non
vérifiable » et n'est pas comptée comme résolue.
"""
import argparse
import csv
import glob
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du dépôt
sys.path.insert(0, ROOT)

from solver.cnf import check_model, parse_dimacs  # noqa: E402
from solver.runner import expected_status  # noqa: E402


def run(path, mode, timeout):
    cmd = [sys.executable, os.path.join(ROOT, "sat.py"), path, "--output-model"]
    if mode:
        cmd += ["--mode", mode]
    cnf = parse_dimacs(path)
    exp = expected_status(path, cnf)
    res = {"instance": path, "expected": exp}
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        res.update(result="TIMEOUT", time=timeout, ok=False)
        return res
    res["time"] = time.perf_counter() - t0
    lines = p.stdout.strip().split("\n")
    if lines == ["s UNSATISFIABLE"]:
        res["result"] = "UNSAT"
        res["ok"] = exp == "UNSAT"
    elif len(lines) == 2 and lines[0] == "s SATISFIABLE" and lines[1].startswith("v ") and lines[1].endswith(" 0"):
        lits = list(map(int, lines[1].split()[1:-1]))
        res["result"] = "SAT"
        res["ok"] = exp == "SAT" and check_model(cnf.clauses, {abs(l): l > 0 for l in lits})
    else:
        res["result"] = "BADFORMAT"
        res["ok"] = False
    return res


def summary(label, rows):
    ok = [r for r in rows if r["ok"]]
    t = [r["time"] for r in ok]
    return (f"{label:40s} instances={len(rows):4d}  correctes={len(ok):4d}  "
            f"timeouts={sum(r['result'] == 'TIMEOUT' for r in rows):3d}  "
            f"fausses={sum(r['result'] != 'TIMEOUT' and not r['ok'] and r['expected'] for r in rows):2d}  "
            f"non vérifiables={sum(r['expected'] is None for r in rows):2d}  "
            f"temps total={sum(t):7.1f} s  médiane={statistics.median(t) if t else 0:5.2f} s  "
            f"max={max(t, default=0):5.2f} s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=["data"])
    ap.add_argument("--mode", default="optimized")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--csv")
    a = ap.parse_args()
    files = []
    for p in a.paths:
        files += [p] if p.endswith(".cnf") else sorted(glob.glob(os.path.join(p, "**", "*.cnf"), recursive=True))
    with ThreadPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(lambda f: run(f, a.mode, a.timeout), files))

    print(f"mode={a.mode}  timeout={a.timeout:g} s  jobs={a.jobs}")
    by_dir = {}
    for r in rows:
        by_dir.setdefault(os.path.relpath(os.path.dirname(r["instance"]), ROOT), []).append(r)
    for d in sorted(by_dir):
        print("  " + summary(d, by_dir[d]))
    print("  " + summary("TOTAL", rows))
    for r in rows:
        if r["result"] == "TIMEOUT":
            print("TIMEOUT", r["instance"])
        elif not r["ok"]:
            print("NON CORRECTE", r)
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["instance", "expected", "result", "time", "ok"])
            w.writeheader()
            w.writerows(rows)
    return 0 if all(r["ok"] or r["result"] == "TIMEOUT" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
