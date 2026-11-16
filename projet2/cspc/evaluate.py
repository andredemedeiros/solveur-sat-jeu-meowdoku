"""Evaluation of expressions: known values are computed, the rest is simplified.

`Evaluator.eval(expr, env)` returns, for an expression of the checked AST:

  - a *known value*: an int, a bool, or an EnumVal;
  - otherwise a ground formula/operand (see ground.py): a Cell, or a
    connective over cells.

`env` maps the loop indices in scope to their value. The evaluation is lazy
(short-circuit): in `a and b`, `a or b` and `a -> b`, the right operand is
not evaluated when the left one decides the result, so a protected access
out of an array is never evaluated, hence never an error.

The expression has been checked beforehand (analyze.py): types are right and
the operands of arithmetic and indices are known. The errors raised here
are the ones that depend on values: an index out of range.
"""

from __future__ import annotations

from itertools import product

from .errors import CompileError
from .ground import (And, Call, Cell, Cmp, Const, Iff, Not, Or, mk_and, mk_cmp, mk_iff, mk_implies,
                     mk_not, mk_or)
from .model import ConstArray, ConstInt, EnumVal, EnumValue, VarArray
import cspc.syntax as ast

BOOL_GLOBALS = ("atLeastOne", "atMostOne", "exactlyOne")
GLOBALS = BOOL_GLOBALS + ("allDifferent",)


def is_known(v) -> bool:
    return isinstance(v, (int, bool, EnumVal))


class Evaluator:
    def __init__(self, symbols: dict):
        self.symbols = symbols

    def eval(self, e, env: dict):
        return getattr(self, "_" + type(e).__name__)(e, env)

    # --- atoms -------------------------------------------------------------

    def _IntLit(self, e, env):
        return e.value

    def _Var(self, e, env):
        if e.name in env:
            return env[e.name]
        sym = self.symbols[e.name]
        if isinstance(sym, ConstInt):
            return sym.value
        if isinstance(sym, EnumValue):
            return sym.value
        return Cell(e.name, ())  # a scalar variable

    def _Index(self, e, env):
        sym = self.symbols[e.name]
        indices = [self.eval(i, env) for i in e.indices]
        return self._access(sym, e, indices)

    def _access(self, sym, e, indices):
        """The case `sym[indices]`: a value for a constant array, else a Cell."""
        if isinstance(sym, ConstArray):
            data = sym.data
            for k, (i, size) in enumerate(zip(indices, sym.dims)):
                self._check_bound(e, k, i, size, is_enum=False)
                data = data[i - 1]
            return data
        index = []
        for k, (i, dim) in enumerate(zip(indices, sym.dims)):
            self._check_bound(e, k, i, dim.size, dim.is_enum)
            index.append(i.index if dim.is_enum else i)
        return Cell(e.name, tuple(index))

    @staticmethod
    def _check_bound(e, k, i, size, is_enum):
        if not is_enum and not 1 <= i <= size:
            raise CompileError(f"index {k + 1} of '{e.name}' is {i}, out of range 1..{size}", e.pos)

    # --- arithmetic ---------------------------------------------------------

    def _Neg(self, e, env):
        return -self.eval(e.expr, env)

    def _Arith(self, e, env):
        a, b = self.eval(e.left, env), self.eval(e.right, env)
        return a + b if e.op == "+" else a - b if e.op == "-" else a * b

    # --- comparisons --------------------------------------------------------

    def _Cmp(self, e, env):
        a, b = self.eval(e.left, env), self.eval(e.right, env)
        if is_known(a) and is_known(b) and not isinstance(a, bool):
            a, b = _number(a), _number(b)
            return {"=": a == b, "!=": a != b, "<": a < b,
                    "<=": a <= b, ">": a > b, ">=": a >= b}[e.op]
        if self._is_boolean(a) or self._is_boolean(b):
            iff = mk_iff(a, b)
            return iff if e.op == "=" else mk_not(iff)
        return mk_cmp(e.op, self._operand(a), self._operand(b))

    def _is_boolean(self, v) -> bool:
        if isinstance(v, bool) or isinstance(v, (Not, And, Or, Iff, Cmp, Call)):
            return True
        return isinstance(v, Cell) and self.symbols[v.array].domain.is_bool

    @staticmethod
    def _operand(v):
        return v if isinstance(v, Cell) else Const(_number(v))

    # --- connectives (lazy) -------------------------------------------------

    def _Not(self, e, env):
        return mk_not(self.eval(e.expr, env))

    def _And(self, e, env):
        left = self.eval(e.left, env)
        if left is False:
            return False
        return mk_and(left, self.eval(e.right, env))

    def _Or(self, e, env):
        left = self.eval(e.left, env)
        if left is True:
            return True
        return mk_or(left, self.eval(e.right, env))

    def _Implies(self, e, env):
        left = self.eval(e.left, env)
        if left is False:
            return True
        return mk_implies(left, self.eval(e.right, env))

    # --- function calls -----------------------------------------------------

    def _Call(self, e, env):
        if e.func == "abs":
            return abs(self.eval(e.args[0], env))
        args = []
        for arg in e.args:
            if isinstance(arg, ast.Comprehension):
                args.extend(self._comprehension(arg, 0, env))
            else:
                args.extend(self._slice(arg, env) if _has_slice(arg) else [self.eval(arg, env)])
        return self._global(e.func, args)

    def _comprehension(self, c, k, env) -> list:
        """The values of `c.expr` for the instances of the ranges satisfying the condition."""
        if k == len(c.ranges):
            if c.cond is not None and self.eval(c.cond, env) is not True:
                return []
            return [self.eval(c.expr, env)]
        r = c.ranges[k]
        if isinstance(r, ast.RangeLoop):
            values = range(self.eval(r.lo, env), self.eval(r.hi, env) + 1)
        else:
            values = self.symbols[r.enum].values
        items = []
        for v in values:
            env[r.var] = v
            items.extend(self._comprehension(c, k + 1, env))
        env.pop(r.var, None)
        return items

    def _slice(self, e, env) -> list:
        """The cases designated by a slice, row by row."""
        sym = self.symbols[e.name]
        dims = sym.dims if isinstance(sym, VarArray) else [None] * len(sym.dims)
        choices = []
        for index, dim in zip(e.indices, dims):
            if isinstance(index, ast.Slice):
                if isinstance(sym, ConstArray):
                    choices.append(range(1, sym.dims[len(choices)] + 1))
                elif dim.is_enum:
                    choices.append(dim.enum.values)
                else:
                    choices.append(range(1, dim.size + 1))
            else:
                choices.append([self.eval(index, env)])
        return [self._access(sym, e, list(idx)) for idx in product(*choices)]

    def _global(self, func, args):
        if func == "allDifferent":
            return self._all_different(args)
        return self._at_most_exactly(func, args)

    @staticmethod
    def _at_most_exactly(func, args):
        if func == "atLeastOne":
            return mk_or(*args)
        trues = sum(1 for a in args if a is True)
        rest = [a for a in args if not isinstance(a, bool)]
        if trues > 1:
            return False
        if trues == 1:  # the others must be false
            return mk_and(*[mk_not(a) for a in rest])
        if func == "atMostOne":
            return True if len(rest) <= 1 else Call(func, tuple(rest))
        # exactlyOne, no known true
        return mk_or(*rest) if len(rest) <= 1 else Call(func, tuple(rest))

    def _all_different(self, args):
        operands = [self._operand(a) for a in args]
        consts = [o.value for o in operands if isinstance(o, Const)]
        if len(set(consts)) < len(consts):
            return False
        if len(consts) == len(operands):
            return True
        return Call("allDifferent", tuple(operands))


def _number(v) -> int:
    """The integer behind a known value: an int, or the number of an enum value."""
    return v.index if isinstance(v, EnumVal) else v


def _has_slice(e) -> bool:
    return isinstance(e, ast.Index) and any(isinstance(i, ast.Slice) for i in e.indices)

