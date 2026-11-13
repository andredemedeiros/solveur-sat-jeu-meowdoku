"""Command line of the constraint compiler: model -> CNF -> solver -> values.

    python csp.py model.csp                  # CNF in Dimacs format on stdout
    python csp.py model.csp --dimacs f.cnf   # CNF written in f.cnf
    python csp.py model.csp --solve          # solve with the solver of part I
    python csp.py model.csp --ast            # print the AST
    python csp.py model.csp --ground         # print the unrolled constraints

Options: --mode {optimized,dpll} (solver), --amo {pairwise,sinz} ("at most
one" encoding), --stats (sizes, on stderr).

--solve prints `s SATISFIABLE` or `s UNSATISFIABLE` and, when satisfiable,
one line `name = value` per variable (`grid[1][2] = 5`, `color[3] = Red`,
`b = true`). An error in the model is reported on stderr with its position,
and the exit code is 1.
"""

import argparse
import sys
import time

from cspc.compiler import compile_text
from cspc.encode import AMO_ENCODINGS
from cspc.errors import CompileError
from cspc.ground import show
from cspc.solving import MODES, solve
from cspc.syntax import parse, pretty
from solver.cnf import to_dimacs_string


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python csp.py", description=__doc__.split("\n")[0])
    p.add_argument("model", help="model file (.csp)")
    p.add_argument("--dimacs", metavar="FILE", help="write the CNF (Dimacs) in FILE")
    p.add_argument("--solve", action="store_true", help="solve and print the values")
    p.add_argument("--ast", action="store_true", help="print the AST and stop")
    p.add_argument("--ground", action="store_true", help="print the unrolled constraints and stop")
    p.add_argument("--mode", choices=MODES, default="optimized", help="solver of part I (default: optimized)")
    p.add_argument("--amo", choices=AMO_ENCODINGS, default="pairwise", help="'at most one' encoding")
    p.add_argument("--stats", action="store_true", help="print sizes and times on stderr")
    return p


def run(args) -> int:
    try:
        with open(args.model, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"{args.model}: {e.strerror}", file=sys.stderr)
        return 2

    try:
        if args.ast:
            print(pretty(parse(text)))
            return 0
        t0 = time.perf_counter()
        compiled = compile_text(text, args.amo)
    except CompileError as e:
        print(e.format(args.model), file=sys.stderr)
        return 1
    compile_time = time.perf_counter() - t0

    report_false_constraints(compiled, args.model)
    if args.ground:
        for c in compiled.expansion.constraints:
            print(show(c.formula))
        return 0

    enc = compiled.encoding
    if args.stats:
        print(f"c compile: {compile_time:.2f}s, {len(compiled.expansion.constraints)} ground constraints, "
              f"{enc.num_named} named variables, {enc.cnf.num_vars} variables, "
              f"{len(enc.cnf.clauses)} clauses", file=sys.stderr)

    if args.dimacs:
        with open(args.dimacs, "w", encoding="utf-8") as f:
            f.write(to_dimacs_string(enc.cnf, enc.comments()))
    elif not args.solve:
        sys.stdout.write(to_dimacs_string(enc.cnf, enc.comments()))

    if args.solve:
        t1 = time.perf_counter()
        sat, values = solve(enc, args.mode)
        if args.stats:
            print(f"c solve: {time.perf_counter() - t1:.2f}s", file=sys.stderr)
        print("s SATISFIABLE" if sat else "s UNSATISFIABLE")
        if sat:
            for name, value in enc.decode(values):
                print(f"{name} = {value}")
    return 0


def report_false_constraints(compiled, filename: str, limit: int = 3):
    """Warn on stderr about constraints that are false whatever the variables."""
    false = compiled.expansion.always_false
    for c in false[:limit]:
        where = f"line {c.pos[0]}, column {c.pos[1]}" if c.pos else "?"
        extra = f" ({c.context})" if c.context else ""
        print(f"{filename}: {where}: warning: constraint{extra} is always false, "
              "the model is unsatisfiable", file=sys.stderr)
    if len(false) > limit:
        print(f"{filename}: warning: {len(false) - limit} more constraints are always false", file=sys.stderr)


def main(argv=None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
