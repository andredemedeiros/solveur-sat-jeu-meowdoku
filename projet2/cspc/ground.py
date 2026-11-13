"""Ground formulas: what a model becomes once loops, slices, names and known
values are gone (question 3).

A ground constraint talks about *cells* only (a variable, or one case of an
array: `grid[1][2]`). The nodes are:

  Cell(array, index)         a cell; used as a formula when it is boolean
  Const(value)               a known integer (an enumerated value is its
                             0-based number in its type), operand of Cmp/Call
  Not / And / Or / Iff       connectives, built by the mk_* functions below
  Cmp(op, left, right)       op in "=", "!=", "<", "<=" between Cell/Const
  Call(func, args)           atMostOne, exactlyOne (boolean arguments) or
                             allDifferent (Cell/Const arguments)
  Lit(n)                     a propositional literal (used by encode.py)

The known booleans are Python's True and False. The mk_* "smart
constructors" fold the known parts and normalise: `not (x = 2)` becomes
`x != 2`, `x > y` is stored as `y < x`, nested And/Or are flattened.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cell:
    array: str
    index: tuple = ()


@dataclass(frozen=True)
class Const:
    value: int


@dataclass(frozen=True)
class Lit:
    """A literal of the CNF: variable number n > 0, or -n for its negation."""
    n: int


@dataclass(frozen=True)
class Not:
    arg: object


@dataclass(frozen=True)
class And:
    args: tuple


@dataclass(frozen=True)
class Or:
    args: tuple


@dataclass(frozen=True)
class Iff:
    left: object
    right: object


@dataclass(frozen=True)
class Cmp:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Call:
    func: str
    args: tuple


# ------------------------------------------------------------
# Smart constructors
# ------------------------------------------------------------

def mk_not(f):
    if isinstance(f, bool):
        return not f
    if isinstance(f, Not):
        return f.arg
    if isinstance(f, Lit):
        return Lit(-f.n)
    if isinstance(f, Cmp):
        # not (a = b) is a != b; not (a < b) is b <= a; and conversely
        flipped = {"=": "!=", "!=": "="}
        if f.op in flipped:
            return Cmp(flipped[f.op], f.left, f.right)
        if f.op == "<":
            return Cmp("<=", f.right, f.left)
        if f.op == "<=":
            return Cmp("<", f.right, f.left)
    return Not(f)


def mk_and(*args):
    flat = []
    for a in args:
        if a is False:
            return False
        if a is True:
            continue
        flat.extend(a.args if isinstance(a, And) else [a])
    if not flat:
        return True
    return flat[0] if len(flat) == 1 else And(tuple(flat))


def mk_or(*args):
    flat = []
    for a in args:
        if a is True:
            return True
        if a is False:
            continue
        flat.extend(a.args if isinstance(a, Or) else [a])
    if not flat:
        return False
    return flat[0] if len(flat) == 1 else Or(tuple(flat))


def mk_implies(a, b):
    return mk_or(mk_not(a), b)


def mk_iff(a, b):
    """a <-> b between booleans (known or not)."""
    if isinstance(a, bool):
        return b if a else mk_not(b)
    if isinstance(b, bool):
        return a if b else mk_not(a)
    if a == b:
        return True
    return Iff(a, b)


def mk_cmp(op, a, b):
    """Comparison between two operands Cell/Const, folded and normalised."""
    if op == ">":
        op, a, b = "<", b, a
    elif op == ">=":
        op, a, b = "<=", b, a
    if isinstance(a, Const) and isinstance(b, Const):
        return {"=": a.value == b.value, "!=": a.value != b.value,
                "<": a.value < b.value, "<=": a.value <= b.value}[op]
    if a == b:
        return op in ("=", "<=")
    if op in ("=", "!=") and isinstance(a, Const):
        a, b = b, a  # the cell first
    return Cmp(op, a, b)


def flatten_and(f) -> list:
    """The conjuncts of a formula (a constant True gives no conjunct)."""
    if f is True:
        return []
    if isinstance(f, And):
        return [c for a in f.args for c in flatten_and(a)]
    return [f]


def show(f) -> str:
    """Readable text of a ground formula (tests, debugging)."""
    if isinstance(f, bool):
        return "true" if f else "false"
    if isinstance(f, Cell):
        return f.array + "".join(f"[{i}]" for i in f.index)
    if isinstance(f, Const):
        return str(f.value)
    if isinstance(f, Lit):
        return f"x{f.n}" if f.n > 0 else f"!x{-f.n}"
    if isinstance(f, Not):
        return f"!{show(f.arg)}"
    if isinstance(f, And):
        return "(" + " /\\ ".join(show(a) for a in f.args) + ")"
    if isinstance(f, Or):
        return "(" + " \\/ ".join(show(a) for a in f.args) + ")"
    if isinstance(f, Iff):
        return f"({show(f.left)} <-> {show(f.right)})"
    if isinstance(f, Cmp):
        return f"{show(f.left)} {f.op} {show(f.right)}"
    if isinstance(f, Call):
        return f"{f.func}({', '.join(show(a) for a in f.args)})"
    raise TypeError(f"show: unexpected {f!r}")
