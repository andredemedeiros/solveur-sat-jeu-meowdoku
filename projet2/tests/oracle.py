"""An independent, naive interpreter of the language, for the tests.

`holds(model, assignment)` tells whether all the constraints of a checked
model are true for a *complete* assignment {(array, index): value} (a bool,
an int, or the number of an enum value). Everything is concrete here: no
simplification, no symbolic value, the plain Python semantics (lazy `and`,
`or`, `->`). The compiler must agree with it on every assignment.
"""

import itertools

import cspc.syntax as ast
from cspc.model import ConstArray, ConstInt, EnumVal, EnumValue


def _num(v):
    return v.index if isinstance(v, EnumVal) else v


def holds(model, assignment) -> bool:
    syms = model.symbols

    def ev(e, env):
        if isinstance(e, ast.IntLit):
            return e.value
        if isinstance(e, ast.Var):
            if e.name in env:
                return _num(env[e.name])
            s = syms[e.name]
            if isinstance(s, ConstInt):
                return s.value
            if isinstance(s, EnumValue):
                return s.value.index
            return assignment[(e.name, ())]
        if isinstance(e, ast.Index):
            idx = [_num(ev(i, env)) for i in e.indices]
            s = syms[e.name]
            if isinstance(s, ConstArray):
                data = s.data
                for i in idx:
                    data = data[i - 1]
                return _num(data)
            return assignment[(e.name, tuple(idx))]
        if isinstance(e, ast.Neg):
            return -ev(e.expr, env)
        if isinstance(e, ast.Arith):
            a, b = ev(e.left, env), ev(e.right, env)
            return {"+": a + b, "-": a - b, "*": a * b}[e.op]
        if isinstance(e, ast.Cmp):
            a, b = ev(e.left, env), ev(e.right, env)
            return {"=": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[e.op]
        if isinstance(e, ast.Not):
            return not ev(e.expr, env)
        if isinstance(e, ast.And):
            return ev(e.left, env) and ev(e.right, env)
        if isinstance(e, ast.Or):
            return ev(e.left, env) or ev(e.right, env)
        if isinstance(e, ast.Implies):
            return (not ev(e.left, env)) or ev(e.right, env)
        if isinstance(e, ast.Call):
            if e.func == "abs":
                return abs(ev(e.args[0], env))
            values = [v for a in e.args for v in items(a, env)]
            if e.func == "atLeastOne":
                return any(values)
            if e.func == "atMostOne":
                return sum(values) <= 1
            if e.func == "exactlyOne":
                return sum(values) == 1
            return len(set(values)) == len(values)  # allDifferent
        raise TypeError(e)

    def items(a, env):
        """Values of one argument of a global constraint: slice, list or expression."""
        if isinstance(a, ast.Comprehension):
            out = []
            for inst in instances(a.ranges, env):
                if a.cond is None or ev(a.cond, inst):
                    out.append(ev(a.expr, inst))
            return out
        if isinstance(a, ast.Index) and any(isinstance(i, ast.Slice) for i in a.indices):
            s = syms[a.name]
            dims = s.dims
            choices = []
            for i, d in zip(a.indices, dims):
                if isinstance(i, ast.Slice):
                    size = d if isinstance(d, int) else d.size
                    choices.append(range(0, size) if getattr(d, "is_enum", False) else range(1, size + 1))
                else:
                    choices.append([ev(i, env)])
            out = []
            for idx in itertools.product(*choices):
                out.append(_const(s, idx) if isinstance(s, ConstArray) else assignment[(a.name, tuple(idx))])
            return out
        return [ev(a, env)]

    def _const(s, idx):
        data = s.data
        for i in idx:
            data = data[i - 1]
        return _num(data)

    def instances(ranges, env):
        pools = []
        for r in ranges:
            if isinstance(r, ast.RangeLoop):
                pools.append((r.var, lambda inst, r=r: range(ev(r.lo, inst), ev(r.hi, inst) + 1)))
            else:
                pools.append((r.var, lambda inst, r=r: range(len(syms[r.enum].values))))

        def go(k, inst):
            if k == len(pools):
                yield dict(inst)
                return
            var, rng = pools[k]
            for v in rng(inst):
                inst[var] = v
                yield from go(k + 1, inst)
            inst.pop(var, None)
        return go(0, dict(env))

    def check(stmt, env):
        if isinstance(stmt, ast.Constraint):
            return bool(ev(stmt.expr, env))
        return all(check(s, inst) for inst in instances(stmt.ranges, env) for s in stmt.body)

    return all(check(s, {}) for s in model.statements)


def all_assignments(model):
    """Every complete assignment of the variables of the model."""
    cells = list(model.cells())
    pools = [[False, True] if d.is_bool else list(d.values) for _, d in cells]
    for combo in itertools.product(*pools):
        yield {(c.array, c.index): v for (c, _), v in zip(cells, combo)}
