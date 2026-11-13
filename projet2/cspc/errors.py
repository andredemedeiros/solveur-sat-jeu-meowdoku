"""Compilation errors: one exception type carrying an optional position."""

from __future__ import annotations

Pos = tuple[int, int]  # (line, column), both starting at 1


class CompileError(Exception):
    """A model rejected by the compiler (syntax, names, types, values...).

    `pos` is the (line, column) of the offending construct in the model
    text, when known. `format()` gives the message shown to the user.
    """

    def __init__(self, message: str, pos: Pos | None = None):
        super().__init__(message)
        self.message = message
        self.pos = pos

    def format(self, filename: str = "<model>") -> str:
        if self.pos is None:
            return f"{filename}: error: {self.message}"
        line, column = self.pos
        return f"{filename}: line {line}, column {column}: {self.message}"
