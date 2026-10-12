#!/usr/bin/env python3
"""Question 6 -- Simulation de la compétition : exécute ``python sat.py``
(sous-processus, comme l'infrastructure officielle) sur un ensemble
d'instances, vérifie le format de sortie, le statut et le modèle, puis
calcule le classement (nb d'instances correctement résolues, temps total).

    python competition.py [--mode optimized|dpll] [--timeout 60] [--jobs 4] [dossiers/fichiers ...]
"""
import argparse
import csv
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from solver.cnf import check_model, parse_dimacs
from solver.runner import expected_status

HERE = os.path.dirname(os.path.abspath(__file__))


def run(path, mode, timeout):
    cmd = [sys.executable, os.path.join(HERE, "sat.py"), path, "--output-model"]
    if mode:
        cmd += ["--mode", mode]
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"instance": path, "result": "TIMEOUT", "time": timeout, "ok": False}
    dt = time.perf_counter() - t0
    lines = p.stdout.strip().split("\n")
    cnf = parse_dimacs(path)
    exp = expected_status(path, cnf)
    res = {"instance": path, "time": dt}
    if lines[0] == "s UNSATISFIABLE" and len(lines) == 1:
        res["result"] = "UNSAT"
        res["ok"] = exp != "SAT"
    elif lines[0] == "s SATISFIABLE" and len(lines) == 2 and lines[1].startswith("v ") and lines[1].endswith(" 0"):
        lits = list(map(int, lines[1].split()[1:-1]))
        res["result"] = "SAT"
        res["ok"] = exp != "UNSAT" and check_model(cnf.clauses, {abs(l): l > 0 for l in lits})
    else:
        res["result"] = "BADFORMAT"
        res["ok"] = False
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=["data/cnf"])
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
    ok = [r for r in rows if r["ok"]]
    print(f"mode={a.mode}  instances={len(rows)}  correctes={len(ok)}  "
          f"timeouts={sum(r['result'] == 'TIMEOUT' for r in rows)}  "
          f"erreurs={sum(r['result'] != 'TIMEOUT' and not r['ok'] for r in rows)}  "
          f"temps total (correctes)={sum(r['time'] for r in ok):.1f} s  max={max((r['time'] for r in ok), default=0):.2f} s")
    for r in rows:
        if not r["ok"] and r["result"] != "TIMEOUT":
            print("ERREUR", r)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["instance", "result", "time", "ok"])
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
