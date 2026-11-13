"""Q6.1 -- Convert a part I grid file into a constraint model.

    python -m tools.grid2csp grid.txt                    # data only
    python -m tools.grid2csp grid.txt --model cells      # data + rules
    python -m tools.grid2csp grid.txt --model general -o grid.csp
"""

import argparse
import sys

from meowdoku.grid import GridError, read_grid

from .meowdoku_models import MODEL_NAMES, build_model, grid_to_data


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.grid2csp", description=__doc__.split("\n")[0])
    p.add_argument("grid", help="grid file (part I format)")
    p.add_argument("--model", choices=MODEL_NAMES, help="also add the rules of this model")
    p.add_argument("-o", "--output", help="output file (default: standard output)")
    args = p.parse_args(argv)
    try:
        grid = read_grid(args.grid)
        text = build_model(grid, args.model) if args.model else grid_to_data(grid)
    except (OSError, GridError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
