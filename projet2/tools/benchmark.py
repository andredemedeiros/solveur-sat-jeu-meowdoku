"""Q6.3, Q6.4, Q6.6 -- Measures: models x solvers on Meowdoku grids of growing size.

    python -m tools.benchmark --sizes 6 8 10 12 --seeds 3 -o results/benchmark.csv

For each grid (planted, hence satisfiable) and each model, the grid is
compiled (time, size of the CNF) and the CNF is given to each solver of
part I (cooperative timeout). The reference "part1" is the dedicated
encoding of part I (meowdoku/encode.py), without the compiler. Each
solution found is verified by the independent checker of part I.
"""

import argparse
import csv
import os
import statistics
import sys
import tempfile
import time
from collections import defaultdict

from cspc.compiler import compile_text
from meowdoku.encode import encode as part1_encode
from meowdoku.generate import generate
from meowdoku.grid import check_solution
from solver import runner
from solver.cnf import write_dimacs

from .meowdoku_models import MODEL_NAMES, build_model, cats_from_values

SOLVERS = ("cdcl", "dpllh:H9", "alg2")   # optimized solver, DPLL with heuristic, plain DPLL of part I
FIELDS = ["size", "seed", "model", "solver", "variables", "clauses", "compile_s", "solve_s", "status", "valid"]


def measure(grid, size, seed, model, solvers, timeout, amo):
    """Rows for one (grid, model): one per solver."""
    if model == "part1":
        t0 = time.perf_counter()
        cnf, enc = part1_encode(grid)
        compile_s = time.perf_counter() - t0
        cell_decode = lambda values: _cats_part1(grid, enc, values)
    else:
        t0 = time.perf_counter()
        compiled = compile_text(build_model(grid, model), amo)
        compile_s = time.perf_counter() - t0
        cnf = compiled.encoding.cnf
        cell_decode = lambda values: cats_from_values(grid, compiled.encoding.decode(values), model)
    fd, path = tempfile.mkstemp(suffix=".cnf")
    os.close(fd)
    write_dimacs(cnf, path)
    rows = []
    try:
        for solver in solvers:
            res = runner.run_one(path, solver, timeout=timeout)
            valid = ""
            if res["status"] == "SAT":
                from solver import cdcl
                # the runner does not return the model: solve again with CDCL only to decode
                # (not timed); the validity concerns the CNF, not the solver under test
                sat, values = cdcl.solve(cnf.clauses, cnf.num_vars)
                valid = not check_solution(grid, cell_decode(values)) if sat else False
            rows.append(dict(size=size, seed=seed, model=model, solver=solver, variables=cnf.num_vars,
                             clauses=len(cnf.clauses), compile_s=round(compile_s, 3),
                             solve_s=round(res["cpu"], 3), status=res["status"], valid=valid))
    finally:
        os.unlink(path)
    return rows


def _cats_part1(grid, enc, values):
    from meowdoku.grid import cats_from_cells
    return cats_from_cells(grid, enc.decode(values))


def summary(rows, solvers=SOLVERS) -> str:
    """Markdown table: size of the CNF, compile time and median solving time (s)
    per (size, model); a `T` marks a timeout among the runs."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["size"], r["model"])].append(r)
    head = "| size | model | variables | clauses | compile (s) | " + " | ".join(f"{s} (s)" for s in solvers) + " |"
    out = [head, "|---|---|---|---|---|" + "---|" * len(solvers)]
    for (size, model), group in sorted(groups.items()):
        cells = []
        for solver in solvers:
            runs = [r for r in group if r["solver"] == solver]
            if not runs:
                cells.append("-")
                continue
            timeout = any(r["status"] == "TIMEOUT" for r in runs)
            cells.append(f"{statistics.median(r['solve_s'] for r in runs):.2f}" + (" T" if timeout else ""))
        out.append(f"| {size} | {model} | {group[0]['variables']} | {group[0]['clauses']} | "
                   f"{statistics.median(r['compile_s'] for r in group):.2f} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.benchmark", description=__doc__.split("\n")[0])
    p.add_argument("--sizes", type=int, nargs="+", default=[6, 8, 10])
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--models", nargs="+", default=["part1", *MODEL_NAMES], choices=["part1", *MODEL_NAMES])
    p.add_argument("--solvers", nargs="+", default=list(SOLVERS))
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--amo", choices=("pairwise", "sinz"), default="pairwise")
    p.add_argument("-o", "--output", default="results/benchmark.csv")
    args = p.parse_args(argv)

    rows = []
    for size in args.sizes:
        for seed in range(args.seeds):
            grid, _ = generate(size, seed=seed)
            for model in args.models:
                if model == "positions" and size > 12:
                    continue   # compile time of the unrolling, see the report
                new = measure(grid, size, seed, model, args.solvers, args.timeout, args.amo)
                rows.extend(new)
                print(" ".join(f"{r['model']}/{r['solver']}:{r['solve_s']}s/{r['status']}" for r in new),
                      f"(n={size}, seed={seed}, compile {new[0]['compile_s']}s)", file=sys.stderr, flush=True)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(summary(rows, args.solvers))
    return 0 if all(r["valid"] in ("", True) for r in rows) else 3


if __name__ == "__main__":
    sys.exit(main())
