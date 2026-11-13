"""The whole chain, from the text of a model to a CNF.

    text --parse--> AST --analyze--> checked model --expand--> ground
    constraints --encode--> CNF --solve--> model --decode--> values
"""

from __future__ import annotations

from dataclasses import dataclass

from .analyze import analyze
from .encode import Encoding, encode
from .expand import Expansion, expand
from .model import Model
from .syntax import parse


@dataclass
class Compiled:
    model: Model
    expansion: Expansion
    encoding: Encoding


def compile_text(text: str, amo: str = "pairwise") -> Compiled:
    """Compile a model; a CompileError is raised if the model is rejected."""
    model = analyze(parse(text))
    expansion = expand(model)
    return Compiled(model, expansion, encode(model, expansion, amo))
