"""Tests of the semantic analysis and of the unrolling (cspc/analyze.py,
evaluate.py, expand.py): erroneous models are rejected with a clear message
and a position; small models give the expected unrolled constraints."""

import pytest

from cspc.analyze import analyze
from cspc.errors import CompileError
from cspc.expand import expand
from cspc.ground import show
from cspc.syntax import parse

PRELUDE = "const N = 3; enum Color = { Red, Green }; var b : bool; var x : 1..3; var y : 1..3; " \
          "var c : Color; array a[3] : 1..3; array g[2][3] : bool; const t[2] = [5, 6];\n"


def compile_ground(text: str):
    model = analyze(parse(PRELUDE + text))
    return [show(c.formula) for c in expand(model).constraints]


def error_of(text: str) -> CompileError:
    with pytest.raises(CompileError) as info:
        compile_ground(text)
    return info.value


ERRORS = [
    # (model, fragment of the message)
    ("constraint w;",                                  "undeclared name 'w'"),
    ("var x : bool;",                                  "'x' is already declared"),
    ("const N = 4;",                                   "'N' is already declared"),
    ("enum E = { Red };",                              "'Red' is already declared"),
    ("enum E = { P, P };",                             "'P' is already declared"),
    ("forall x in 1..2 { constraint b; }",             "'x' is already declared"),
    ("forall i in 1..2, i in 1..2 { constraint b; }",  "'i' is already declared"),
    ("constraint x;",                                  "a constraint must be boolean"),
    ("constraint x = c;",                              "cannot compare integer with value of enum Color"),
    ("constraint b = x;",                              "cannot compare boolean with integer"),
    ("constraint b < b;",                              "booleans can only be compared with = and !="),
    ("constraint c < 2;",                              "cannot compare"),
    ("constraint b + 1 = 2;",                          "arithmetic needs integers"),
    ("constraint x + 1 = y;",                          "arithmetic is only allowed on known values"),
    ("constraint -x = 1;",                             "arithmetic is only allowed on known values"),
    ("constraint a[x] = 1;",                           "index 1 of 'a' must be a known value"),
    ("constraint a[b] = 1;",                           "index 1 of 'a' must be of type integer"),
    ("constraint a = 1;",                              "'a' is an array: it needs 1 indices"),
    ("constraint a[1][2] = 1;",                        "'a' has 1 dimension(s), but 2 index(es)"),
    ("constraint x[1] = 1;",                           "'x' is not an array"),
    ("constraint N[1] = 1;",                           "'N' is not an array"),
    ("constraint Color;",                              "'Color' is a type, not a value"),
    ("constraint a[1] = a[*];",                        "a slice is only allowed as an argument"),
    ("constraint a[*] = 1;",                           "a slice is only allowed as an argument"),
    ("constraint b and x;",                            "a boolean is expected here"),
    ("constraint not x;",                              "a boolean is expected here"),
    ("constraint g[1][1] -> N;",                       "a boolean is expected here"),
    ("constraint allDifferent(b, b);",                 "allDifferent expects integers or enumerated values"),
    ("constraint allDifferent(x, c);",                 "arguments must have the same type"),
    ("constraint allDifferent();",                     "expects at least one argument"),
    ("constraint atMostOne(x, y);",                    "atMostOne expects boolean arguments"),
    ("constraint foo(x);",                             "unknown function 'foo'"),
    ("constraint abs(1, 2) = 1;",                      "abs expects 1 argument"),
    ("constraint abs(x) = 1;",                         "the argument of abs must be a known value"),
    ("array z[0] : bool;",                             "must be positive"),
    ("array z[x] : bool;",                             "must be a known value"),
    ("array z[b] : bool;",                             "must be of type integer"),
    ("var z : 3..1;",                                  "empty interval 3..1"),
    ("var z : x..3;",                                  "must be a known value"),
    ("var z : Nope;",                                  "undeclared name 'Nope'"),
    ("var z : N;",                                     "'N' is not an enumerated type"),
    ("const z = x;",                                   "must be a known value"),
    ("const z = b;",                                   "must be of type integer"),
    ("const z[2] = [1];",                              "expects 2 items here, not 1"),
    ("const z[2] = [1, [2]];",                         "too many dimensions"),
    ("const z[2][2] = [1, 2];",                        "expects a list of 2 items here"),
    ("const z[2] = [1, Red];",                         "must all have the same type"),
    ("const z[1] = [x];",                              "must be known integers or enum values"),
    ("forall i in x..3 { constraint b; }",             "the lower bound of a loop must be a known value"),
    ("forall i in 1..3 { constraint i; }",             "a constraint must be boolean"),
    ("forall c2 in N { constraint b; }",               "'N' is not an enumerated type"),
    ("constraint atLeastOne(b forall i in 1..2 : x = 1);", "the condition of a list must be a known value"),
    ("constraint atLeastOne(b) and (b forall i in 1..2);", "syntax error"),
    # errors that depend on values
    ("constraint t[3] = 1;",                           "index 1 of 't' is 3, out of range 1..2"),
    ("constraint a[0] = 1;",                           "index 1 of 'a' is 0, out of range 1..3"),
    ("constraint g[1][4];",                            "index 2 of 'g' is 4, out of range 1..3"),
    ("forall i in 1..4 { constraint a[i] = 1; }",      "index 1 of 'a' is 4, out of range 1..3"),
    ("forall i in 1..3 { constraint a[i + 1] = 1; }",  "index 1 of 'a' is 4, out of range 1..3"),
]


@pytest.mark.parametrize("text, message", ERRORS)
def test_errors(text, message):
    err = error_of(text)
    assert message in err.message, err.message
    assert err.pos is not None or message == "syntax error"


def test_error_positions():
    err = error_of("constraint x = 1 and\n    a[x] = 2;")
    assert err.pos == (3, 7)  # the offending index, on the line after the prelude
    assert err.format("m.csp").startswith("m.csp: line 3, column 7: ")
    err = error_of("forall i in 1..2 {\n  constraint a[i + 2] = 1;\n}")
    assert err.pos == (3, 14)


UNROLLED = [
    # (model, expected ground constraints)
    ("constraint b;",                                 ["b"]),
    ("constraint b and not b;",                       ["b", "!b"]),               # top-level and: two constraints
    ("constraint x = 2;",                             ["x = 2"]),
    ("constraint x = 2 and y != 1;",                  ["x = 2", "y != 1"]),
    ("constraint x > y;",                             ["y < x"]),                 # normalisation
    ("constraint x >= y;",                            ["y <= x"]),
    ("constraint 2 < x;",                             ["2 < x"]),
    ("constraint not (x = 2);",                      ["x != 2"]),
    ("constraint not (x < y);",                      ["y <= x"]),
    ("constraint not not b;",                        ["b"]),
    ("constraint 1 + 2 * 3 = 7;",                    []),                          # true: disappears
    ("constraint N * N = 9 and x = N;",               ["x = 3"]),
    ("constraint abs(2 - N) = 1 and b;",              ["b"]),
    ("constraint c = Green;",                         ["c = 1"]),                 # enum values are numbers
    ("constraint c != Red;",                          ["c != 0"]),
    ("constraint Red < Green;",                       []),
    ("constraint t[1] = 5 and t[2] = x;",             ["x = 6"]),                 # constant array
    ("constraint a[2] = a[N];",                       ["a[2] = a[3]"]),
    ("constraint g[2][3] or g[1][1];",                ["(g[2][3] \\/ g[1][1])"]),
    ("constraint b -> x = 1;",                        ["(!b \\/ x = 1)"]),
    ("constraint (b and x = 1) = (y = 2);",           ["((b /\\ x = 1) <-> y = 2)"]),
    ("constraint b = (x = 1);",                       ["(b <-> x = 1)"]),
    ("constraint b != (x = 1);",                      ["!(b <-> x = 1)"]),
    ("constraint (x = 1) = (1 = 1);",                 ["x = 1"]),
    ("constraint x = x;",                             []),
    ("constraint x < x;",                             ["false"]),
    ("constraint allDifferent(a[*]);",                ["allDifferent(a[1], a[2], a[3])"]),
    ("constraint allDifferent(x, 2, a[1]);",          ["allDifferent(x, 2, a[1])"]),
    ("constraint allDifferent(1, 2, 3);",             []),
    ("constraint allDifferent(1, 1);",                ["false"]),
    ("constraint atMostOne(g[2][*]);",                ["atMostOne(g[2][1], g[2][2], g[2][3])"]),
    ("constraint atMostOne(g[*][*]);",
     ["atMostOne(g[1][1], g[1][2], g[1][3], g[2][1], g[2][2], g[2][3])"]),   # row by row
    ("constraint atLeastOne(g[1][*]);",               ["(g[1][1] \\/ g[1][2] \\/ g[1][3])"]),
    ("constraint exactlyOne(b, x = 1);",              ["exactlyOne(b, x = 1)"]),
    ("constraint exactlyOne(b);",                     ["b"]),
    ("constraint exactlyOne(b, 1 = 1, x = 1);",       ["!b", "x != 1"]),
    ("constraint atMostOne(b, 1 = 1, 2 = 2);",        ["false"]),
    ("constraint atMostOne(g[1][*], g[2][*]) and 1 = 2;", ["false"]),
    ("constraint atLeastOne(g[1][i] forall i in 1..3 : i != 2);", ["(g[1][1] \\/ g[1][3])"]),
    ("constraint atMostOne(g[i][i] forall i in 1..2);", ["atMostOne(g[1][1], g[2][2])"]),
    # loops
    ("forall i in 1..3 { constraint a[i] = i; }",     ["a[1] = 1", "a[2] = 2", "a[3] = 3"]),
    ("forall i in 2..1 { constraint b; }",            []),                          # empty loop
    ("forall i in 1..2, j in i..2 { constraint g[i][j]; }", ["g[1][1]", "g[1][2]", "g[2][2]"]),
    ("forall k in Color { constraint c = k; }",       ["c = 0", "c = 1"]),
    ("forall i in 1..2 { forall j in 1..2 { constraint g[i][j]; } }",
     ["g[1][1]", "g[1][2]", "g[2][1]", "g[2][2]"]),
    ("forall i in 1..3 { constraint a[i] = i; constraint b; }",
     ["a[1] = 1", "b", "a[2] = 2", "b", "a[3] = 3", "b"]),
    # lazy evaluation: a false condition protects an access out of range
    ("forall i in 1..3 { constraint i < 3 -> a[i + 1] != a[i]; }",
     ["a[2] != a[1]", "a[3] != a[2]"]),
    ("forall i in 1..3 { constraint i < 3 and a[i + 1] != a[i]; }",
     ["a[2] != a[1]", "a[3] != a[2]", "false"]),                                   # i = 3: false, and protected
    ("forall i in 1..3 { constraint i = 3 or a[i + 1] != a[i]; }",
     ["a[2] != a[1]", "a[3] != a[2]"]),
    ("forall i in 1..3 { constraint not (i < 3) or a[i + 1] != a[i]; }",
     ["a[2] != a[1]", "a[3] != a[2]"]),
    ("forall i in 1..3 { constraint i >= 1 and i <= 3 -> a[i] = i; }",
     ["a[1] = 1", "a[2] = 2", "a[3] = 3"]),
    ("forall i in 0..4 { constraint i >= 1 and i <= 3 -> a[i] = 1; }",
     ["a[1] = 1", "a[2] = 1", "a[3] = 1"]),
]


@pytest.mark.parametrize("text, expected", UNROLLED)
def test_unrolling(text, expected):
    assert compile_ground(text) == expected


def test_always_false_is_reported():
    model = analyze(parse(PRELUDE + "forall i in 1..3 { constraint i != 2; }"))
    result = expand(model)
    assert len(result.always_false) == 1
    assert result.always_false[0].context == "i=2"
    assert result.always_false[0].pos == (2, 20)


def test_scope_of_loop_indices():
    # the index is not visible after the loop
    err = error_of("forall i in 1..2 { constraint b; }\nconstraint i = 1;")
    assert "undeclared name 'i'" in err.message
    # but the name can be reused by another loop
    assert compile_ground("forall i in 1..2 { constraint b; } forall i in 1..2 { constraint b; }") == ["b"] * 4


def test_use_before_declaration():
    err = error_of("constraint z;\nvar z : bool;")
    assert "undeclared name 'z'" in err.message
