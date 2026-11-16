"""Semantic analysis (question 3): symbol table and checks.

`analyze(program)` processes the statements in order and returns a `Model`.
It rejects, before any translation, the models that are syntactically
correct but meaningless: undeclared or redeclared name, incompatible types,
unknown value where a known one is required (`x + 1 = y`), wrong number of
indices, slice outside a global constraint, wrong arguments of a global...

An index out of range depends on values and is detected later, during the
unrolling (evaluate.py), because a false condition may protect it.

Each expression gets a type and a *known* flag (computed from the
compilation alone: literals, constants, enum values, loop indices, cells of
constant arrays, and what is computed from them).
"""

from __future__ import annotations

import cspc.syntax as ast
from .errors import CompileError
from .evaluate import BOOL_GLOBALS, GLOBALS, Evaluator
from .model import (BOOL, INT, ConstArray, ConstInt, Dim, Domain, EnumType, EnumVal, EnumValue,
                    LoopVar, Model, Ty, VarArray, enum_ty)


def analyze(program: ast.Program) -> Model:
    return Analyzer().run(program)


class Analyzer:
    def __init__(self):
        self.model = Model()
        self.symbols = self.model.symbols
        self.evaluator = Evaluator(self.symbols)

    def run(self, program: ast.Program) -> Model:
        for stmt in program.statements:
            if isinstance(stmt, (ast.Constraint, ast.Forall)):
                self.check_statement(stmt, dict(self.symbols))
                self.model.statements.append(stmt)
            else:
                self.declare(stmt)
        return self.model

    # ------------------------------------------------------------------
    # Declarations
    # ------------------------------------------------------------------

    def declare(self, stmt):
        getattr(self, "_declare_" + type(stmt).__name__)(stmt)

    def new_name(self, name, pos, scope=None):
        if name in (self.symbols if scope is None else scope):
            raise CompileError(f"name '{name}' is already declared", pos)

    def known_value(self, e, what, ty=INT):
        """Check that `e` is a known value of type `ty` and compute it."""
        self.expect_known(e, self.symbols, ty, what)
        return self.evaluator.eval(e, {})

    def expect_known(self, e, scope, ty, what):
        t, known = self.expr(e, scope)
        if t != ty:
            raise CompileError(f"{what} must be of type {ty}, not {t}", e.pos)
        if not known:
            raise CompileError(f"{what} must be a known value (constants and loop indices only)", e.pos)

    def _declare_ConstDecl(self, d):
        self.new_name(d.name, d.pos)
        self.symbols[d.name] = ConstInt(self.known_value(d.value, f"the value of constant '{d.name}'"))

    def _declare_EnumDecl(self, d):
        self.new_name(d.name, d.pos)
        values = []
        for i, name in enumerate(d.values):
            if name == d.name:  # the type itself is only registered after its values
                raise CompileError(f"name '{name}' is already declared", d.pos)
            self.new_name(name, d.pos)
            self.symbols[name] = EnumValue(EnumVal(d.name, i, name))  # also detects duplicates
            values.append(self.symbols[name].value)
        self.symbols[d.name] = EnumType(d.name, values)

    def _declare_ConstArrayDecl(self, d):
        self.new_name(d.name, d.pos)
        dims = [self.size(dim, f"dimension of '{d.name}'") for dim in d.dims]
        types = set()
        data = self.const_data(d.value, dims, d.name, types)
        if len(types) != 1:
            raise CompileError(f"the elements of '{d.name}' must all have the same type", d.pos)
        self.symbols[d.name] = ConstArray(dims, data, types.pop())

    def const_data(self, lit, dims, name, types):
        """The nested lists of a constant array, checked against its dimensions."""
        if not isinstance(lit, ast.ArrayLit):
            raise CompileError(f"'{name}' expects a list of {dims[0]} items here", lit.pos)
        if len(lit.items) != dims[0]:
            raise CompileError(f"'{name}' expects {dims[0]} items here, not {len(lit.items)}", lit.pos)
        if len(dims) > 1:
            return [self.const_data(item, dims[1:], name, types) for item in lit.items]
        data = []
        for item in lit.items:
            if isinstance(item, ast.ArrayLit):
                raise CompileError(f"too many dimensions for '{name}'", item.pos)
            t, known = self.expr(item, dict(self.symbols))
            if t.kind == "bool" or not known:
                raise CompileError(f"the elements of '{name}' must be known integers or enum values", item.pos)
            types.add(t)
            data.append(self.evaluator.eval(item, {}))
        return data

    def size(self, e, what) -> int:
        n = self.known_value(e, what)
        if n < 1:
            raise CompileError(f"{what} must be positive, not {n}", e.pos)
        return n

    def domain(self, d: ast.Domain) -> Domain:
        if isinstance(d, ast.RangeDomain):
            lo = self.known_value(d.lo, "the lower bound of an interval")
            hi = self.known_value(d.hi, "the upper bound of an interval")
            if lo > hi:
                raise CompileError(f"empty interval {lo}..{hi}", d.pos)
            return Domain(INT, tuple(range(lo, hi + 1)))
        if d.name == "bool":
            return Domain(BOOL, (0, 1))
        enum = self.enum_type(d.name, d.pos)
        return Domain(enum_ty(enum.name), tuple(range(len(enum.values))))

    def enum_type(self, name, pos) -> EnumType:
        sym = self.symbols.get(name)
        if not isinstance(sym, EnumType):
            raise CompileError(f"'{name}' is not an enumerated type" if name in self.symbols
                               else f"undeclared name '{name}'", pos)
        return sym

    def dim(self, e, owner) -> Dim:
        """A dimension: a known size, or the name of an enum type."""
        if isinstance(e, ast.Var) and isinstance(self.symbols.get(e.name), EnumType):
            enum = self.symbols[e.name]
            return Dim(len(enum.values), enum)
        return Dim(self.size(e, f"dimension of '{owner}'"))

    def _declare_VarDecl(self, d):
        self.new_name(d.name, d.pos)
        var = VarArray(d.name, [], self.domain(d.domain))
        self.symbols[d.name] = var
        self.model.variables.append(var)

    def _declare_ArrayDecl(self, d):
        self.new_name(d.name, d.pos)
        dims = [self.dim(e, d.name) for e in d.dims]
        var = VarArray(d.name, dims, self.domain(d.domain))
        self.symbols[d.name] = var
        self.model.variables.append(var)

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------

    def check_statement(self, stmt, scope):
        if isinstance(stmt, ast.Constraint):
            t, _ = self.expr(stmt.expr, scope)
            if t != BOOL:
                raise CompileError(f"a constraint must be boolean, not {t}", stmt.expr.pos)
            return
        scope = self.bind_loops(stmt.ranges, scope)
        for s in stmt.body:
            self.check_statement(s, scope)

    def bind_loops(self, ranges, scope):
        """The scope extended with the indices of the loop ranges (checked in order)."""
        scope = dict(scope)
        for r in ranges:
            self.new_name(r.var, r.pos, scope)
            if isinstance(r, ast.RangeLoop):
                self.expect_known(r.lo, scope, INT, "the lower bound of a loop")
                self.expect_known(r.hi, scope, INT, "the upper bound of a loop")
                scope[r.var] = LoopVar(INT)
            else:
                enum = self.enum_type(r.enum, r.pos)
                scope[r.var] = LoopVar(enum_ty(enum.name))
        return scope

    # ------------------------------------------------------------------
    # Expressions: (type, known)
    # ------------------------------------------------------------------

    def expr(self, e, scope) -> tuple[Ty, bool]:
        return getattr(self, "_expr_" + type(e).__name__)(e, scope)

    def lookup(self, name, pos, scope):
        if name not in scope:
            raise CompileError(f"undeclared name '{name}'", pos)
        return scope[name]

    def _expr_IntLit(self, e, scope):
        return INT, True

    def _expr_Var(self, e, scope):
        sym = self.lookup(e.name, e.pos, scope)
        if isinstance(sym, ConstInt):
            return INT, True
        if isinstance(sym, EnumValue):
            return enum_ty(sym.value.enum), True
        if isinstance(sym, LoopVar):
            return sym.ty, True
        if isinstance(sym, VarArray) and not sym.dims:
            return sym.domain.ty, False
        if isinstance(sym, (VarArray, ConstArray)):
            raise CompileError(f"'{e.name}' is an array: it needs {len(sym.dims)} indices", e.pos)
        raise CompileError(f"'{e.name}' is a type, not a value", e.pos)

    def _expr_Comprehension(self, e, scope):
        raise CompileError("a list 'e forall ...' is only allowed as the argument of a global constraint", e.pos)

    def _expr_Slice(self, e, scope):
        raise CompileError("'*' is only allowed as an index", e.pos)

    def _expr_Index(self, e, scope):
        if any(isinstance(i, ast.Slice) for i in e.indices):
            raise CompileError("a slice is only allowed as an argument of a global constraint", e.pos)
        return self.indexed(e, scope)

    def indexed(self, e, scope, slices_ok=False):
        """Type of `name[i][j]...` (slices allowed or not): (element type, known)."""
        sym = self.lookup(e.name, e.pos, scope)
        if not isinstance(sym, (VarArray, ConstArray)) or not sym.dims:
            raise CompileError(f"'{e.name}' is not an array", e.pos)
        if len(e.indices) != len(sym.dims):
            raise CompileError(f"'{e.name}' has {len(sym.dims)} dimension(s), "
                               f"but {len(e.indices)} index(es) are given", e.pos)
        for k, (index, dim) in enumerate(zip(e.indices, sym.dims), start=1):
            if isinstance(index, ast.Slice):
                continue
            want = enum_ty(dim.enum.name) if isinstance(dim, Dim) and dim.is_enum else INT
            self.expect_known(index, scope, want, f"index {k} of '{e.name}'")
        if isinstance(sym, ConstArray):
            return sym.ty, True
        return sym.domain.ty, False

    def _expr_Call(self, e, scope):
        if e.func == "abs":
            if len(e.args) != 1:
                raise CompileError(f"abs expects 1 argument, not {len(e.args)}", e.pos)
            self.expect_known(e.args[0], scope, INT, "the argument of abs")
            return INT, True
        if e.func not in GLOBALS:
            raise CompileError(f"unknown function '{e.func}'", e.pos)
        if not e.args:
            raise CompileError(f"{e.func} expects at least one argument", e.pos)
        types = []
        for arg in e.args:
            if isinstance(arg, ast.Comprehension):
                inner = self.bind_loops(arg.ranges, scope)
                types.append((self.expr(arg.expr, inner)[0], arg))
                if arg.cond is not None:
                    self.expect_known(arg.cond, inner, BOOL, "the condition of a list")
            elif isinstance(arg, ast.Index) and any(isinstance(i, ast.Slice) for i in arg.indices):
                types.append((self.indexed(arg, scope)[0], arg))
            else:
                types.append((self.expr(arg, scope)[0], arg))
        if e.func in BOOL_GLOBALS:
            for t, arg in types:
                if t != BOOL:
                    raise CompileError(f"{e.func} expects boolean arguments, not {t}", arg.pos)
        else:
            first = types[0][0]
            if first.kind == "bool":
                raise CompileError("allDifferent expects integers or enumerated values, not booleans",
                                   types[0][1].pos)
            for t, arg in types:
                if t != first:
                    raise CompileError(f"allDifferent arguments must have the same type: {first} and {t}",
                                       arg.pos)
        return BOOL, False

    def arith_operand(self, e, scope):
        t, known = self.expr(e, scope)
        if t != INT:
            raise CompileError(f"arithmetic needs integers, not {t}", e.pos)
        if not known:
            raise CompileError("arithmetic is only allowed on known values "
                               "(constants and loop indices), not on variables", e.pos)

    def _expr_Neg(self, e, scope):
        self.arith_operand(e.expr, scope)
        return INT, True

    def _expr_Arith(self, e, scope):
        self.arith_operand(e.left, scope)
        self.arith_operand(e.right, scope)
        return INT, True

    def _expr_Cmp(self, e, scope):
        (a, ka), (b, kb) = self.expr(e.left, scope), self.expr(e.right, scope)
        if a != b:
            raise CompileError(f"cannot compare {a} with {b}", e.pos)
        if a.kind == "bool" and e.op not in ("=", "!="):
            raise CompileError(f"booleans can only be compared with = and !=, not {e.op}", e.pos)
        return BOOL, ka and kb

    def _connective(self, e, scope, operands):
        known = True
        for operand in operands:
            t, k = self.expr(operand, scope)
            if t != BOOL:
                raise CompileError(f"a boolean is expected here, not {t}", operand.pos)
            known = known and k
        return BOOL, known

    def _expr_Not(self, e, scope):
        return self._connective(e, scope, [e.expr])

    def _expr_And(self, e, scope):
        return self._connective(e, scope, [e.left, e.right])

    _expr_Or = _expr_And
    _expr_Implies = _expr_And
