"""
Command line: parse a model of the propositional fragment and print its AST.

Run from the proplog/ folder:

    python csp.py model.csp

A syntax error is reported with its position, on stderr.
"""

import argparse
import sys

from lark.exceptions import UnexpectedInput

from syntax import parse, pretty


def main():
    parser = argparse.ArgumentParser(
        prog="python csp.py",
        description="Parse a model of the propositional fragment and print its AST",
    )
    parser.add_argument("model", help="model file (.csp)")
    args = parser.parse_args()

    with open(args.model) as f:
        text = f.read()

    try:
        program = parse(text)
    except UnexpectedInput as e:
        print(f"{args.model}: {e}", file=sys.stderr)
        sys.exit(1)

    print(pretty(program))


if __name__ == "__main__":
    main()
