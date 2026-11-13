"""The symbol table and the checked model (question 3).

All names (constants, types, enumerated values, variables, arrays, loop
indices) share one namespace, kept in a dict name -> symbol. The symbols
are the dataclasses below. `Model` is what `analyze` returns: the symbols,
plus the statements that remain to be unrolled (constraints and loops).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Iterator

from .ground import Cell

# ------------------------------------------------------------
# Types and known values
# ------------------------------------------------------------

@dataclass(frozen=True)
class Ty:
    """Type of an expression: integer, boolean, or value of an enum."""
    kind: str                 # "int", "bool" or "enum"
    enum: str | None = None   # name of the enum type, for kind == "enum"

    def __str__(self):
        return {"int": "integer", "bool": "boolean"}.get(self.kind) or f"value of enum {self.enum}"


INT = Ty("int")
BOOL = Ty("bool")


def enum_ty(name: str) -> Ty:
    return Ty("enum", name)


@dataclass(frozen=True)
class EnumVal:
    """A known value of an enumerated type; ordered by declaration order."""
    enum: str
    index: int
    name: str


# ------------------------------------------------------------
# Symbols
# ------------------------------------------------------------

@dataclass
class ConstInt:
    value: int

@dataclass
class ConstArray:
    dims: list          # sizes
    data: list          # nested lists of int / EnumVal
    ty: Ty

@dataclass
class EnumType:
    name: str
    values: list        # list of EnumVal

@dataclass
class EnumValue:
    value: EnumVal

@dataclass
class LoopVar:
    ty: Ty


@dataclass
class Domain:
    """Domain of a variable: its type and its values (enums: 0..k-1)."""
    ty: Ty
    values: tuple

    @property
    def is_bool(self) -> bool:
        return self.ty.kind == "bool"


@dataclass
class Dim:
    """A dimension of an array: a size n (indices 1..n) or an enum type."""
    size: int
    enum: EnumType | None = None

    @property
    def is_enum(self) -> bool:
        return self.enum is not None


@dataclass
class VarArray:
    """A variable (no dimension) or an array of variables."""
    name: str
    dims: list
    domain: Domain

    def indices(self) -> Iterator[tuple]:
        """All the index tuples, row by row (enum dims: 0-based numbers)."""
        ranges = [range(0, d.size) if d.is_enum else range(1, d.size + 1) for d in self.dims]
        return product(*ranges)

    def cells(self) -> Iterator[Cell]:
        return (Cell(self.name, idx) for idx in self.indices())


@dataclass
class Model:
    """A checked model: symbols, variable declarations, statements to unroll."""
    symbols: dict = field(default_factory=dict)
    variables: list = field(default_factory=list)    # VarArray, in declaration order
    statements: list = field(default_factory=list)   # Constraint / Forall, checked

    def cells(self) -> Iterator[tuple]:
        """Every (Cell, Domain) of the model, in declaration order."""
        for var in self.variables:
            for cell in var.cells():
                yield cell, var.domain

    def domain_of(self, cell: Cell) -> Domain:
        return self.symbols[cell.array].domain

    def index_name(self, var: VarArray, k: int, i: int) -> str:
        """Text of the index i of dimension k of `var`: a number or an enum value."""
        dim = var.dims[k]
        return dim.enum.values[i].name if dim.is_enum else str(i)

    def cell_name(self, cell: Cell) -> str:
        """`grid[1][2]`, `row[A]`, `x`."""
        var = self.symbols[cell.array]
        return cell.array + "".join(f"[{self.index_name(var, k, i)}]" for k, i in enumerate(cell.index))

    def value_name(self, domain: Domain, value: int) -> str:
        """Text of the value of a cell: an integer or the name of an enum value."""
        if domain.ty.kind == "enum":
            return self.symbols[domain.ty.enum].values[value].name
        return str(value)
