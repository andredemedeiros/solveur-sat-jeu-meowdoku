"""
Tests of the parser of the propositional fragment (syntax.py): precedence
and associativity, syntax errors, the examples, and the pretty-printer.

Run from the proplog/ folder:  python -m tests.test_syntax  (or: pytest)

Each test is a plain function with asserts (no pytest needed); an error
stops the script with the failing case.
"""

from pathlib import Path

from lark.exceptions import UnexpectedInput

from syntax import And, Implies, Not, Or, Var, parse, pretty

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

a, b, c = Var("a"), Var("b"), Var("c")


def parse_expr(text):
    """The AST of one expression, e.g. parse_expr("a or b") is Or(a, b)."""
    program = parse(f"constraint {text};")
    return program.statements[0].expr


def test_precedence():
    cases = [
        ("a or b and c",    Or(a, And(b, c))),
        ("a and b or c",    Or(And(a, b), c)),
        ("not a and b",     And(Not(a), b)),
        ("not (a and b)",   Not(And(a, b))),
        ("a or b -> c",     Implies(Or(a, b), c)),
        ("a -> b or c",     Implies(a, Or(b, c))),
        ("not a -> b",      Implies(Not(a), b)),
        ("not not a",       Not(Not(a))),
        ("((a))",           a),
    ]
    for text, expected in cases:
        assert parse_expr(text) == expected, text


def test_associativity():
    cases = [
        ("a and b and c",   And(And(a, b), c)),       # left
        ("a or b or c",     Or(Or(a, b), c)),         # left
        ("a -> b -> c",     Implies(a, Implies(b, c))),   # right
        ("(a -> b) -> c",   Implies(Implies(a, b), c)),
    ]
    for text, expected in cases:
        assert parse_expr(text) == expected, text


def test_syntax_errors():
    # each model, with the position of the error
    cases = [
        ("var x : int;",                        (1, 9)),    # bool is the only domain
        ("var x : bool",                        (1, 9)),    # missing ";": Lark gives the last token
        ("var x : bool; constraint x or;",      (1, 30)),
        ("constraint (x and y;",                (1, 20)),
        ("constraint x y;",                     (1, 14)),
        ("var and : bool;",                     (1, 5)),    # a keyword is not a name
        ("constraint x = y;",                   (1, 14)),   # not in the fragment
        ("constraint x <-> y;",                 (1, 14)),   # no <-> in the language
        ("var x : bool;\nconstraint x\nvar y : bool;", (3, 1)),
    ]
    for text, (line, column) in cases:
        try:
            parse(text)
        except UnexpectedInput as e:
            assert (e.line, e.column) == (line, column), (text, e.line, e.column)
        else:
            raise AssertionError(f"no syntax error in {text!r}")


def test_examples():
    # every example parses, except syntax-error.csp
    for path in sorted(EXAMPLES.glob("*.csp")):
        try:
            parse(path.read_text())
        except UnexpectedInput:
            assert path.name == "syntax-error.csp", path.name
        else:
            assert path.name != "syntax-error.csp", path.name


def test_pretty():
    program = parse("var x : bool;\n"
                    "var y : bool;\n"
                    "constraint not x and y -> x or y;\n")
    assert pretty(program) == ("Program\n"
                               "  Var x : bool\n"
                               "  Var y : bool\n"
                               "  Constraint (((!x) /\\ y) -> (x \\/ y))")


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print(f"{name}: ok")
