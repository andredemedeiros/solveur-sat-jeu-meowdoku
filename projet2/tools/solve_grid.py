"""Q6.2 -- Solve a Meowdoku grid with one of the constraint models, and verify
the solution with the independent checker of part I (meowdoku/grid.py).

    python -m tools.solve_grid grid.txt --model cells
"""

import argparse
import sys
import time
from dataclasses import dataclass

from cspc.compiler import compile_text
from cspc.errors import CompileError
from cspc.solving import MODES, solve
from meowdoku.grid import Grid, check_solution, format_solution, read_grid

from .meowdoku_models import MODEL_NAMES, build_model, cats_from_values


@dataclass
class Run:
    """Measures of one resolution of a grid with a model."""
    model: str
    satisfiable: bool
    cats: dict | None
    errors: list           # rules violated by the solution (must be empty)
    variables: int
    clauses: int
    compile_s: float
    solve_s: float


def run_model(grid: Grid, name: str, amo: str = "pairwise", mode: str = "optimized") -> Run:
    text = build_model(grid, name)
    t0 = time.perf_counter()
    compiled = compile_text(text, amo)
    t1 = time.perf_counter()
    enc = compiled.encoding
    sat, values = solve(enc, mode)
    t2 = time.perf_counter()
    cats, errors = None, []
    if sat:
        cats = cats_from_values(grid, enc.decode(values), name)
        errors = check_solution(grid, cats)
    return Run(name, sat, cats, errors, enc.cnf.num_vars, len(enc.cnf.clauses), t1 - t0, t2 - t1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.solve_grid", description=__doc__.split("\n")[0])
    p.add_argument("grid", help="grid file (part I format)")
    p.add_argument("--model", choices=MODEL_NAMES, default="general")
    p.add_argument("--amo", choices=("pairwise", "sinz"), default="pairwise")
    p.add_argument("--mode", choices=MODES, default="optimized")
    args = p.parse_args(argv)
    try:
        grid = read_grid(args.grid)
        run = run_model(grid, args.model, args.amo, args.mode)
    except (OSError, ValueError, CompileError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"c model {run.model}: {run.variables} variables, {run.clauses} clauses, "
          f"compile {run.compile_s:.2f}s, solve {run.solve_s:.2f}s", file=sys.stderr)
    if not run.satisfiable:
        print("s UNSATISFIABLE")
        return 0
    print("s SATISFIABLE")
    sys.stdout.write(format_solution(grid, run.cats))
    if run.errors:
        print("INVALID SOLUTION:\n  " + "\n  ".join(run.errors), file=sys.stderr)
        return 3
    print("c solution verified", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
