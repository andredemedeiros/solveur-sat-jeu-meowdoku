"""
Tests of the parser (cspc/syntax.py): precedence and associativity of the
whole language, syntax errors with their position, the examples, the
pretty-printer and the round trip parse(source(ast)) == ast.

Run from the project folder:  python -m pytest tests   (or: python -m tests.test_syntax)
"""

from pathlib import Path

from cspc.errors import CompileError
from cspc.syntax import (And, Arith, ArrayDecl, Call, Cmp, Comprehension, Constraint, EnumLoop, Forall,
                         Implies, Index, IntLit, Neg, Not, Or, RangeDomain, RangeLoop, Slice, Var,
                         parse, pretty, source)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
MODELS = [*sorted((ROOT / "exemples").glob("*.csp")), *sorted((ROOT / "models").rglob("*.csp"))]

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
        ("var x : 1..;",                        (1, 12)),   # missing upper bound
        ("var x : bool",                        (1, 9)),    # missing ";": Lark gives the last token
        ("var x : bool; constraint x or;",      (1, 30)),
        ("constraint (x and y;",                (1, 20)),
        ("constraint x y;",                     (1, 14)),
        ("var and : bool;",                     (1, 5)),    # a keyword is not a name
        ("constraint x <-> y;",                 (1, 15)),   # no <-> in the language
        ("constraint a = b = c;",               (1, 18)),   # comparisons do not chain
        ("constraint x +;",                     (1, 15)),
        ("const N = 3",                         (1, 11)),
        ("var forall : bool;",                  (1, 5)),    # all the keywords are reserved
        ("var in : bool;",                      (1, 5)),
        ("var const : bool;",                   (1, 5)),
        ("forall i in 1..3 { var x : bool; }",  (1, 20)),   # no declaration in a loop
        ("const t[2] = [1, 2;",                 (1, 19)),
        ("constraint f(1,);",                   (1, 16)),
        ("var x : bool;\nconstraint x\nvar y : bool;", (3, 1)),
    ]
    for text, (line, column) in cases:
        try:
            parse(text)
        except CompileError as e:
            assert e.pos == (line, column), (text, e.pos)
        else:
            raise AssertionError(f"no syntax error in {text!r}")


def test_examples():
    # every example parses, except syntax-error.csp
    for path in sorted(EXAMPLES.glob("*.csp")):
        try:
            parse(path.read_text())
        except CompileError:
            assert path.name == "syntax-error.csp", path.name
        else:
            assert path.name != "syntax-error.csp", path.name


def test_precedence_of_the_full_language():
    x, y = Var("x"), Var("y")
    one, two = IntLit(1), IntLit(2)
    cases = [
        ("not x = 2",               Not(Cmp("=", x, two))),             # not looser than comparison
        ("x = 1 and y != 2",        And(Cmp("=", x, one), Cmp("!=", y, two))),
        ("x + 1 = y * 2",           Cmp("=", Arith("+", x, one), Arith("*", y, two))),
        ("1 + 2 * x",               None),                              # checked below on arithmetic
        ("x - y - 1 = 0",           Cmp("=", Arith("-", Arith("-", x, y), one), IntLit(0))),
        ("-x * 2 = 1",              Cmp("=", Arith("*", Neg(x), two), one)),
        ("x < 1 -> y >= 2 -> x",    Implies(Cmp("<", x, one), Implies(Cmp(">=", y, two), x))),
        ("(x = 1) = (y = 2)",       Cmp("=", Cmp("=", x, one), Cmp("=", y, two))),
    ]
    for text, expected in cases:
        if expected is not None:
            assert parse_expr(text) == expected, text
    assert parse_expr("1 + 2 * x") == Arith("+", one, Arith("*", two, x))


def test_arrays_calls_and_slices():
    assert parse_expr("g[i][1]") == Index("g", [Var("i"), IntLit(1)])
    assert parse_expr("allDifferent(g[i][*], g[*][1], x)") == Call(
        "allDifferent", [Index("g", [Var("i"), Slice()]), Index("g", [Slice(), IntLit(1)]), Var("x")])
    assert parse_expr("f()") == Call("f", [])
    assert parse_expr("abs(x - 1)") == Call("abs", [Arith("-", Var("x"), IntLit(1))])
    # the list extension: sole argument of a function
    lst = parse_expr("atLeastOne(c[i] forall i in 1..3 : i != 2)").args[0]
    assert isinstance(lst, Comprehension) and lst.cond is not None and len(lst.ranges) == 1


def test_declarations_and_loops():
    program = parse("array g[N][Color] : 1..N;\n"
                    "forall i in 1..N, c in Color { constraint g[i][c] != 1; }")
    decl, loop = program.statements
    assert isinstance(decl, ArrayDecl) and decl.dims == [Var("N"), Var("Color")]
    assert decl.domain == RangeDomain(IntLit(1), Var("N"))
    assert isinstance(loop, Forall)
    assert [type(r) for r in loop.ranges] == [RangeLoop, EnumLoop]
    assert isinstance(loop.body[0], Constraint)


def test_keywords_are_not_prefixes_of_names():
    # `variable`, `index`, `android`, `format`, `constant` are names, not keywords
    program = parse("var variable : bool; var index : bool; var android : bool; "
                    "constraint format or constant;")
    assert [s.name for s in program.statements[:3]] == ["variable", "index", "android"]


def test_comments_and_positions():
    program = parse("// comment\nconst N = 3; // another\n  constraint x;\n")
    assert program.statements[0].pos == (2, 1)
    assert program.statements[1].pos == (3, 3)
    assert program.statements[1].expr.pos == (3, 14)


def test_models_round_trip():
    # the text printed by source() parses back to the same tree
    for path in [*EXAMPLES.glob("*.csp"), *MODELS]:
        try:
            program = parse(path.read_text())
        except CompileError:
            assert path.name == "syntax-error.csp"
            continue
        assert parse(source(program)) == program, path


def test_models_parse():
    for path in MODELS:   # (the Meowdoku rules need their data to be checked, not to be parsed)
        parse(path.read_text())


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
