"""Unrolling (question 3): from the checked model to a list of ground constraints.

Every `forall` is replaced by its instances (the loop indices take their
values), and each constraint is evaluated with the Evaluator: known parts
are computed, slices are replaced by the cells they designate, and the
result is a constraint without loop, name or arithmetic, over cells only.
A top-level conjunction gives several constraints; a constraint that
simplifies to true disappears; one that simplifies to false is kept (the
model is unsatisfiable) and reported in `Expansion.always_false`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cspc.syntax as ast
from .evaluate import Evaluator
from .ground import flatten_and
from .model import Model


@dataclass
class GroundConstraint:
    formula: object
    pos: tuple | None = None      # position of the constraint in the model text
    context: str = ""             # loop indices of the instance: "i=2, j=3"


@dataclass
class Expansion:
    constraints: list = field(default_factory=list)
    always_false: list = field(default_factory=list)   # GroundConstraint simplified to false


def expand(model: Model) -> Expansion:
    return Expander(model).run()


class Expander:
    def __init__(self, model: Model):
        self.model = model
        self.evaluator = Evaluator(model.symbols)
        self.result = Expansion()

    def run(self) -> Expansion:
        for stmt in self.model.statements:
            self.statement(stmt, {})
        return self.result

    def statement(self, stmt, env: dict):
        if isinstance(stmt, ast.Constraint):
            self.constraint(stmt, env)
        else:
            self.loop(stmt, 0, env)

    def loop(self, forall: ast.Forall, k: int, env: dict):
        """Run the body for every value of the loop indices ranges[k:]."""
        if k == len(forall.ranges):
            for stmt in forall.body:
                self.statement(stmt, env)
            return
        r = forall.ranges[k]
        if isinstance(r, ast.RangeLoop):
            values = range(self.evaluator.eval(r.lo, env), self.evaluator.eval(r.hi, env) + 1)
        else:
            values = self.model.symbols[r.enum].values
        for v in values:
            env[r.var] = v
            self.loop(forall, k + 1, env)
        env.pop(r.var, None)

    def constraint(self, stmt: ast.Constraint, env: dict):
        formula = self.evaluator.eval(stmt.expr, env)
        context = ", ".join(f"{name}={getattr(v, 'name', v)}" for name, v in env.items())
        for conjunct in flatten_and(formula):
            ground = GroundConstraint(conjunct, stmt.pos, context)
            self.result.constraints.append(ground)
            if conjunct is False:
                self.result.always_false.append(ground)
