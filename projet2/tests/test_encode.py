"""Validation of the translation to CNF (questions 1, 4): the compiler is
compared with the naive interpreter of tests/oracle.py on random small models.

For every complete assignment of the variables, "the oracle accepts it" must
be equivalent to "the CNF plus the unit clauses fixing the named variables
is satisfiable" (an exact check: the auxiliary variables are free). And the
model found by the solver, decoded, must be accepted by the oracle.
"""

import random

import pytest

from cspc.compiler import compile_text
from solver import cdcl

from .oracle import all_assignments, holds

PRELUDE = """
enum E = { P, Q, R };
const T[3] = [2, 1, 3];
var b1 : bool; var b2 : bool;
var x : 1..3; var y : 2..4;
var e1 : E; var e2 : E;
array a[2] : 1..2;
array g[2] : bool;
"""
CELLS_WITH = {"b": ["b1", "b2", "g[1]", "g[2]"], "i": ["x", "y", "a[1]", "a[2]"], "e": ["e1", "e2"]}


class RandomModel:
    """Random constraints over the prelude above, well typed by construction."""

    def __init__(self, rng):
        self.rng = rng

    def boolean(self, depth):
        r = self.rng
        if depth == 0 or r.random() < 0.25:
            return r.choice(CELLS_WITH["b"])
        kind = r.choice(["and", "or", "not", "implies", "icmp", "icmp", "ecmp", "bcmp", "global", "global"])
        if kind == "and":
            return f"({self.boolean(depth - 1)} and {self.boolean(depth - 1)})"
        if kind == "or":
            return f"({self.boolean(depth - 1)} or {self.boolean(depth - 1)})"
        if kind == "not":
            return f"(not {self.boolean(depth - 1)})"
        if kind == "implies":
            return f"({self.boolean(depth - 1)} -> {self.boolean(depth - 1)})"
        if kind == "icmp":
            return f"({self.integer()} {r.choice(['=', '!=', '<', '<=', '>', '>='])} {self.integer()})"
        if kind == "ecmp":
            return f"({self.enum()} {r.choice(['=', '!=', '<', '<=', '>', '>='])} {self.enum()})"
        if kind == "bcmp":
            return f"({self.boolean(depth - 1)} {r.choice(['=', '!='])} {self.boolean(depth - 1)})"
        return self.global_call(depth)

    def global_call(self, depth):
        r = self.rng
        func = r.choice(["atLeastOne", "atMostOne", "exactlyOne", "allDifferent", "allDifferent"])
        if func == "allDifferent":
            if r.random() < 0.5:
                args = [self.integer() for _ in range(r.randint(1, 4))]
            else:
                args = [self.enum() for _ in range(r.randint(1, 3))]
            if r.random() < 0.3:
                args = ["a[*]", r.choice(["x", "T[1]", "3"])]
        else:
            args = [self.boolean(depth - 1) for _ in range(r.randint(1, 4))]
            if r.random() < 0.3:
                args = ["g[*]"]
            elif r.random() < 0.2:
                args = ["g[k] forall k in 1..2"]
        return f"{func}({', '.join(args)})"

    def integer(self):
        r = self.rng
        return r.choice(CELLS_WITH["i"] + ["T[2]", "0", "1", "2", "3", "4", "(1 + 2)"])

    def enum(self):
        return self.rng.choice(CELLS_WITH["e"] + ["P", "Q", "R"])

    def model(self):
        constraints = "\n".join(f"constraint {self.boolean(3)};" for _ in range(self.rng.randint(1, 3)))
        return PRELUDE + constraints + "\n"


def check_equivalence(text, amo):
    compiled = compile_text(text, amo)
    model, enc = compiled.model, compiled.encoding
    clauses = enc.cnf.clauses
    for assignment in all_assignments(model):
        units = []
        for (cell, value), n in enc.var_of.items():
            domain = model.domain_of(cell)
            actual = assignment[(cell.array, cell.index)]
            on = actual if domain.is_bool else actual == value
            units.append([n if on else -n])
        sat, _ = cdcl.solve(clauses + units, enc.cnf.num_vars)
        assert sat == holds(model, assignment), (text, assignment, amo)
    # the model returned by the solver is a solution
    sat, values = cdcl.solve(clauses, enc.cnf.num_vars)
    assert sat == any(holds(model, a) for a in all_assignments(model))
    if sat:
        decoded = dict(enc.decode(values))
        chosen = {}
        for cell, domain in model.cells():
            v = decoded[model.cell_name(cell)]
            chosen[(cell.array, cell.index)] = (v == "true") if domain.is_bool else \
                (model.symbols[domain.ty.enum].values[[x.name for x in model.symbols[domain.ty.enum].values].index(v)].index
                 if domain.ty.kind == "enum" else int(v))
        assert holds(model, chosen), text


@pytest.mark.parametrize("amo", ["pairwise", "sinz"])
@pytest.mark.parametrize("seed", range(40))
def test_random_models(seed, amo):
    text = RandomModel(random.Random(seed)).model()
    check_equivalence(text, amo)


def test_domain_clauses_for_x_in_1_3():
    """The example of the statement: x : 1..3 gives x1 v x2 v x3 and 3 binary clauses."""
    enc = compile_text("var x : 1..3;").encoding
    assert sorted(map(sorted, enc.cnf.clauses)) == [[-3, -2], [-3, -1], [-2, -1], [1, 2, 3]]


def test_comparisons_of_the_statement():
    """x = 2 is x2, x != 2 is -x2; x != y gives one binary clause per value."""
    def clauses(constraint):
        enc = compile_text(f"var x : 1..3; var y : 1..3; constraint {constraint};").encoding
        return [sorted(c) for c in enc.cnf.clauses[8:]]   # after the two domains (4 clauses each)
    assert clauses("x = 2") == [[2]]
    assert clauses("x != 2") == [[-2]]
    assert clauses("x <= 2") == [[-3]]                    # the shortest of x1 v x2 and -x3
    assert clauses("x != y") == [[-4, -1], [-5, -2], [-6, -3]]


def test_every_comparison_between_every_pair_of_domains():
    for op in ["=", "!=", "<", "<=", ">", ">="]:
        for dx, dy in [("1..3", "1..3"), ("1..2", "2..4"), ("1..1", "1..3"), ("3..5", "1..3")]:
            text = f"var x : {dx}; var y : {dy}; constraint x {op} y; constraint x {op} 2; constraint 3 {op} y;"
            check_equivalence(text, "pairwise")


def test_global_under_negation_is_exact():
    """atMostOne under a negation or an implication: the pairwise encoding is exact."""
    for amo in ("pairwise", "sinz"):
        check_equivalence("var p : bool; var q : bool; var r : bool; var s : bool; var t : bool;"
                          "constraint s -> not atMostOne(p, q, r);"
                          "constraint t = exactlyOne(p, q, r);", amo)


def test_equality_between_comparisons():
    """= and != between two non-elementary booleans (comparisons, connectives)."""
    for amo in ("pairwise", "sinz"):
        check_equivalence("var x : 1..3; var y : 1..3; var p : bool;"
                          "constraint (x = 2) = (y = 3);"
                          "constraint (x < 2) != (y <= 2) or p;"
                          "constraint (x != y) = (p and x = 1);", amo)


def test_sequential_counter_sizes():
    """Sinz: 3n - 4 clauses and n - 1 auxiliary variables for atMostOne of n literals."""
    n = 10
    names = "".join(f"var p{i} : bool;" for i in range(n))
    args = ", ".join(f"p{i}" for i in range(n))
    pair = compile_text(f"{names} constraint atMostOne({args});", "pairwise").encoding.cnf
    sinz = compile_text(f"{names} constraint atMostOne({args});", "sinz").encoding.cnf
    assert len(pair.clauses) == n * (n - 1) // 2 and pair.num_vars == n
    assert len(sinz.clauses) == 3 * n - 4 and sinz.num_vars == n + n - 1


def test_constant_false_gives_unsat():
    enc = compile_text("var b : bool; constraint 1 = 2;").encoding
    assert [] in enc.cnf.clauses
