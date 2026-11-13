"""Translation to CNF (question 4).

1. *Direct encoding of the domains.* A variable x of domain {v1..vk} is
   represented by k booleans x_v1..x_vk ("x = v"), with the clauses
   "exactly one" (one clause "at least one", and "at most one" pairwise or
   by sequential counter). A bool variable is one boolean.
2. *Comparisons* and *global constraints* become propositional formulas
   over these booleans (see `Encoder.compare` and `Encoder.call`).
3. *CNF.* A formula is put in negation normal form, then in CNF with the
   Plaisted-Greenbaum variant of Tseitin's transformation: an auxiliary
   variable `a` is introduced for a conjunction nested under a disjunction
   and only the implication `a -> sub-formula` is stated (enough since the
   formula is in NNF, `a` occurs positively). When a constraint is already
   a clause, or a disjunction of one conjunction of literals, no auxiliary
   variable is needed.

Variables 1..`num_named` are the booleans of the cells, in declaration
order (what `decode` reads back); the following ones are auxiliary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from solver.cnf import CNF

from .expand import Expansion
from .ground import (And, Call, Cell, Cmp, Iff, Lit, Not, Or, flatten_and, mk_and, mk_iff,
                     mk_not, mk_or)
from .model import Model

AMO_ENCODINGS = ("pairwise", "sinz")


@dataclass
class Encoding:
    """The result of the translation: a CNF and how to read a model back."""
    cnf: CNF
    model: Model
    var_of: dict = field(default_factory=dict)   # (Cell, value) -> variable number
    num_named: int = 0

    def comments(self) -> list[str]:
        """`var n name` lines (DIMACS comments): what each named boolean means."""
        out = []
        for (cell, value), n in self.var_of.items():
            domain = self.model.domain_of(cell)
            name = self.model.cell_name(cell)
            out.append(f"var {n} {name}" if domain.is_bool
                       else f"var {n} {name}={self.model.value_name(domain, value)}")
        return out

    def decode(self, values: dict) -> list[tuple[str, str]]:
        """(name, value) of every cell, from a model {variable: bool}."""
        result = {}
        for (cell, value), n in self.var_of.items():
            domain = self.model.domain_of(cell)
            if domain.is_bool:
                result[cell] = "true" if values.get(n, False) else "false"
            elif values.get(n, False):
                result[cell] = self.model.value_name(domain, value)
        return [(self.model.cell_name(c), v) for c, v in result.items()]


def encode(model: Model, expansion: Expansion, amo: str = "pairwise") -> Encoding:
    enc = Encoder(model, amo)
    for c in expansion.constraints:
        enc.add_constraint(c.formula)
    return enc.finish()


class Encoder:
    def __init__(self, model: Model, amo: str = "pairwise"):
        if amo not in AMO_ENCODINGS:
            raise ValueError(f"unknown 'at most one' encoding {amo!r}")
        self.model = model
        self.amo = amo
        self.num_vars = 0
        self.clauses: list[list[int]] = []
        self.var_of: dict = {}
        self.domains = {v.name: v.domain for v in model.variables}
        for cell, domain in model.cells():
            self.encode_domain(cell, domain)
        self.num_named = self.num_vars

    def finish(self) -> Encoding:
        cnf = CNF(self.num_vars, self.clauses)
        return Encoding(cnf, self.model, self.var_of, self.num_named)

    # ------------------------------------------------------------------
    # Variables and domains
    # ------------------------------------------------------------------

    def new_var(self) -> int:
        self.num_vars += 1
        return self.num_vars

    def encode_domain(self, cell: Cell, domain):
        if domain.is_bool:
            self.var_of[(cell, 1)] = self.new_var()
            return
        lits = []
        for v in domain.values:
            self.var_of[(cell, v)] = self.new_var()
            lits.append(self.num_vars)
        self.clauses.append(list(lits))                  # at least one value
        self.amo_clauses([Lit(n) for n in lits])        # at most one value

    def atom(self, cell: Cell, value: int):
        """The literal "cell = value"; False if the value is not in the domain."""
        if self.domains[cell.array].is_bool:
            n = self.var_of[(cell, 1)]
            return Lit(n if value else -n)
        n = self.var_of.get((cell, value))
        return Lit(n) if n else False

    def values(self, cell: Cell) -> tuple:
        return self.domains[cell.array].values

    # ------------------------------------------------------------------
    # Ground formula -> propositional formula
    # ------------------------------------------------------------------

    def translate(self, f):
        if isinstance(f, bool):
            return f
        if isinstance(f, Cell):
            return self.atom(f, 1)
        if isinstance(f, Not):
            return mk_not(self.translate(f.arg))
        if isinstance(f, And):
            return mk_and(*[self.translate(a) for a in f.args])
        if isinstance(f, Or):
            return mk_or(*[self.translate(a) for a in f.args])
        if isinstance(f, Iff):
            return mk_iff(self.translate(f.left), self.translate(f.right))
        if isinstance(f, Cmp):
            return self.compare(f)
        if isinstance(f, Call):
            return self.call(f)
        raise TypeError(f"translate: unexpected {f!r}")

    def compare(self, f: Cmp):
        """`x op c`, `c op x` or `x op y` as a formula over the booleans of the domains.

        Several translations exist; the ones chosen (all correct because
        exactly one boolean of each domain is true):
          x = c, x != c   one literal (or its negation);
          x < c, ...      the shortest of "x takes one of the good values"
                          (a clause) and "x takes none of the bad values"
                          (a conjunction of unit literals);
          x = y           x_v -> y_v for each v: |dom| binary clauses;
          x != y          not (x_v and y_v) for each common v;
          x < y, x <= y   x_v -> (y_w1 or y_w2 ...) for each v: one clause of
                          at most |dom| literals per value, rather than
                          |dom|^2/2 binary clauses.
        """
        left, right, op = f.left, f.right, f.op
        if isinstance(left, Cell) and isinstance(right, Cell):
            return self.compare_cells(op, left, right)
        if isinstance(left, Cell):          # x op c
            c = right.value
            test = {"=": lambda u: u == c, "!=": lambda u: u != c,
                    "<": lambda u: u < c, "<=": lambda u: u <= c}[op]
            return self.satisfying(left, test)
        c = left.value                      # c op x  (only < and <=: = and != put the cell first)
        test = {"<": lambda u: c < u, "<=": lambda u: c <= u}[op]
        return self.satisfying(right, test)

    def satisfying(self, cell: Cell, test):
        """The values of `cell` satisfying `test`, as the shortest formula."""
        good = [u for u in self.values(cell) if test(u)]
        bad = [u for u in self.values(cell) if not test(u)]
        if len(good) <= len(bad):
            return mk_or(*[self.atom(cell, u) for u in good])
        return mk_and(*[mk_not(self.atom(cell, u)) for u in bad])

    def compare_cells(self, op, x: Cell, y: Cell):
        dx, dy = self.values(x), set(self.values(y))
        parts = []
        for u in dx:
            if op == "=":
                parts.append(mk_or(mk_not(self.atom(x, u)), self.atom(y, u)))
            elif op == "!=":
                parts.append(mk_or(mk_not(self.atom(x, u)), mk_not(self.atom(y, u))) if u in dy else True)
            else:
                above = [w for w in self.values(y) if (w > u if op == "<" else w >= u)]
                parts.append(mk_or(mk_not(self.atom(x, u)), *[self.atom(y, w) for w in above]))
        return mk_and(*parts)

    # --- global constraints --------------------------------------------

    def call(self, f: Call):
        """A global constraint inside a formula: always the exact pairwise
        encoding, valid under any connective, negation included."""
        if f.func == "allDifferent":
            return mk_and(*[self.amo_formula(items) for items in self.value_items(f)])
        lits = [self.lit_of(self.translate(a)) for a in f.args]
        at_most = self.amo_formula(lits)
        return at_most if f.func == "atMostOne" else mk_and(mk_or(*lits), at_most)

    def value_items(self, f: Call):
        """For allDifferent: for each value v, the list "argument = v" of the arguments."""
        values = sorted({v for a in f.args for v in (self.values(a) if isinstance(a, Cell) else [a.value])})
        return [[self.atom(a, v) if isinstance(a, Cell) else a.value == v for a in f.args]
                for v in values]

    @staticmethod
    def amo_formula(items):
        """At most one of the items (literals or known booleans), pairwise."""
        return mk_and(*[mk_or(mk_not(items[i]), mk_not(items[j]))
                        for i in range(len(items)) for j in range(i + 1, len(items))])

    def amo_clauses(self, items):
        """Add the clauses "at most one of the items" with the chosen encoding."""
        trues = sum(1 for i in items if i is True)
        lits = [i for i in items if isinstance(i, Lit)]
        if trues > 1:
            self.clauses.append([])
        elif trues == 1:
            for lit in lits:
                self.add_clause([-lit.n])
        elif self.amo == "sinz" and len(lits) > 2:
            self.sinz([l.n for l in lits])
        else:
            for i in range(len(lits)):
                for j in range(i + 1, len(lits)):
                    self.add_clause([-lits[i].n, -lits[j].n])

    def sinz(self, xs):
        """Sequential counter of Sinz: 3n - 4 clauses, n - 1 auxiliary variables.
        s_i means "one of x_1..x_i is true". Only valid for a constraint that
        is asserted (not under a negation or a disjunction)."""
        n = len(xs)
        s = [self.new_var() for _ in range(n - 1)]
        self.add_clause([-xs[0], s[0]])
        for i in range(1, n - 1):
            self.add_clause([-xs[i], s[i]])
            self.add_clause([-s[i - 1], s[i]])
            self.add_clause([-xs[i], -s[i - 1]])
        self.add_clause([-xs[n - 1], -s[n - 2]])

    # ------------------------------------------------------------------
    # Constraints -> clauses
    # ------------------------------------------------------------------

    def add_constraint(self, ground):
        """Assert a ground constraint."""
        for c in flatten_and(ground):
            if isinstance(c, Call) and self.amo != "pairwise":
                self.assert_call(c)
            else:
                self.add_formula(self.translate(c))

    def assert_call(self, f: Call):
        """A global constraint asserted at top level: the chosen "at most one" encoding."""
        if f.func == "allDifferent":
            for items in self.value_items(f):
                self.amo_clauses(items)
            return
        lits = [self.lit_of(self.translate(a)) for a in f.args]
        if f.func == "exactlyOne":
            self.add_formula(mk_or(*lits))
        self.amo_clauses(lits)

    def lit_of(self, f):
        """A literal equivalent to the formula f (known booleans stay as they are)."""
        if isinstance(f, (bool, Lit)):
            return f
        a = Lit(self.new_var())
        self.add_formula(mk_or(mk_not(a), f))   # a -> f
        self.add_formula(mk_or(a, mk_not(f)))   # f -> a
        return a

    def nnf(self, f, negated: bool):
        """Negation normal form of f (or of not f): And/Or over Lit and booleans."""
        if isinstance(f, bool):
            return f != negated
        if isinstance(f, Lit):
            return mk_not(f) if negated else f
        if isinstance(f, Not):
            return self.nnf(f.arg, not negated)
        if isinstance(f, (And, Or)):
            conj = isinstance(f, And) != negated
            parts = [self.nnf(a, negated) for a in f.args]
            return mk_and(*parts) if conj else mk_or(*parts)
        if isinstance(f, Iff):
            a, b = self.lit_of(f.left), self.lit_of(f.right)
            if negated:
                b = mk_not(b)
            return mk_and(mk_or(mk_not(a), b), mk_or(a, mk_not(b)))
        raise TypeError(f"nnf: unexpected {f!r}")

    def add_formula(self, f):
        for c in flatten_and(self.nnf(f, False)):
            self.add_disjunction(c)

    def add_disjunction(self, c):
        """Add the clauses for c: a literal, False, or an Or of literals and conjunctions."""
        if c is False:
            self.clauses.append([])
        elif isinstance(c, Lit):
            self.add_clause([c.n])
        else:
            lits = [a.n for a in c.args if isinstance(a, Lit)]
            ands = [a for a in c.args if isinstance(a, And)]
            if len(ands) == 1 and all(isinstance(a, Lit) for a in ands[0].args):
                for a in ands[0].args:              # l or (a and b)  =  (l or a) and (l or b)
                    self.add_clause(lits + [a.n])
                return
            for conj in ands:
                lits.append(self.define(conj))
            self.add_clause(lits)

    def define(self, conj: And) -> int:
        """An auxiliary variable `a` with a -> conj (`a` occurs positively only)."""
        a = self.new_var()
        for part in conj.args:
            self.add_disjunction(mk_or(Lit(-a), part))
        return a

    def add_clause(self, lits):
        lits = list(dict.fromkeys(lits))
        if not any(-l in lits for l in lits):   # skip tautologies
            self.clauses.append(lits)
