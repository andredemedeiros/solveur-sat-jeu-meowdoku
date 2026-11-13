r"""
Syntax of the constraint language: grammar (Lark, LALR), AST, builder,
pretty-printer and source printer.

    text --(Lark parser)--> parse tree --(ASTBuilder)--> AST

The parse tree is Lark's generic tree. The AST is made of our own
dataclasses, one class per construct, which the later passes walk with
isinstance. Every node remembers its position (line, column) in the text,
for error messages; the position is ignored when comparing two nodes.

Example:

    var x : bool;
    constraint not x and y -> x or y;

gives, as printed by pretty():

    Program
      Var x : bool
      Constraint (((!x) /\ y) -> (x \/ y))
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lark import Lark, Transformer, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedToken

from .errors import CompileError, Pos

# ------------------------------------------------------------
# Grammar
# ------------------------------------------------------------
# Notation: "?rule" is inlined when it has a single child; "-> name" names
# the alternative (and thus the ASTBuilder method); "..." strings are
# matched then dropped. The "basic" lexer cuts the whole text into tokens
# before parsing, so keywords (var, in, and, ...) are always keyword
# tokens, never names: they are reserved.
#
# Precedence, from the loosest to the tightest, by layering the rules:
#   ->  <  or  <  and  <  not  <  comparison  <  + -  <  *  <  unary -  <  atom
# A comparison is not recursive: `a = b = c` is a syntax error. Since
# `not` is looser than comparisons, `not x = 2` is `not (x = 2)`.
#   a or b and c   is  a or (b and c)       a -> b -> c   is  a -> (b -> c)
#   a or b or c    is  (a or b) or c        a - b - c     is  (a - b) - c

GRAMMAR = r"""
?start: program

program: statement*

?statement: const_decl
          | const_array_decl
          | enum_decl
          | var_decl
          | array_decl
          | constraint_decl
          | forall_stmt

// -------------------- DECLARATIONS --------------------

const_decl: "const" NAME "=" expr ";"
const_array_decl: "const" NAME dim+ "=" array_lit ";"
enum_decl: "enum" NAME "=" "{" NAME ("," NAME)* "}" ";"
var_decl: "var" NAME ":" domain ";"
array_decl: "array" NAME dim+ ":" domain ";"

dim: "[" expr "]"

array_lit: "[" lit_item ("," lit_item)* "]"
?lit_item: array_lit
         | expr

// bool, an integer interval a..b, or the name of an enumerated type
domain: "bool"                          -> bool_domain
      | arith ".." arith                -> range_domain
      | NAME                            -> named_domain

// -------------------- STATEMENTS --------------------

constraint_decl: "constraint" expr ";"

forall_stmt: "forall" loop_range ("," loop_range)* "{" body_stmt* "}"
?body_stmt: constraint_decl
          | forall_stmt

loop_range: NAME "in" arith ".." arith  -> range_loop
          | NAME "in" NAME              -> enum_loop

// -------------------- EXPRESSIONS --------------------

?expr: implication

?implication: or_expr
            | or_expr "->" implication  -> implies

?or_expr: and_expr
        | or_expr "or" and_expr         -> or_op

?and_expr: not_expr
         | and_expr "and" not_expr      -> and_op

?not_expr: "not" not_expr               -> not_op
         | comparison

?comparison: arith
           | arith "="  arith           -> eq
           | arith "!=" arith           -> ne
           | arith "<"  arith           -> lt
           | arith "<=" arith           -> le
           | arith ">"  arith           -> gt
           | arith ">=" arith           -> ge

?arith: term
      | arith "+" term                  -> add
      | arith "-" term                  -> sub

?term: unary
     | term "*" unary                   -> mul

?unary: "-" unary                       -> neg
      | atom

?atom: INT                              -> int_lit
     | NAME                             -> var_ref
     | NAME index+                      -> index_ref
     | NAME "(" args? ")"               -> call
     | NAME "(" comprehension ")"       -> call
     | "(" expr ")"

index: "[" expr "]"
     | "[" "*" "]"                      -> slice_index

args: expr ("," expr)*

// Extension: the list of the e such that cond, in a global constraint:
//   atLeastOne(cat[i][j] forall i in 1..N, j in 1..M : region[i][j] = z)
// (no new keyword: it reuses forall and ":")
comprehension: expr "forall" loop_range ("," loop_range)* (":" expr)?

%import common.CNAME -> NAME
%import common.INT
%import common.WS
%import common.CPP_COMMENT
%ignore WS
%ignore CPP_COMMENT
"""


# ------------------------------------------------------------
# AST
# ------------------------------------------------------------

@dataclass
class Node:
    """Base of all nodes: `pos` is the position in the text (not compared)."""
    pos: Pos | None = field(default=None, compare=False, repr=False, kw_only=True)


# Domains

class Domain(Node):
    pass

@dataclass
class EnumDomain(Domain):
    """`bool`, or the name of an enumerated type (`var c : Color;`)."""
    name: str

@dataclass
class RangeDomain(Domain):
    """`lo..hi`: an interval of integers."""
    lo: object
    hi: object


# Statements

@dataclass
class Program(Node):
    statements: list

@dataclass
class ConstDecl(Node):
    """`const N = 9;`"""
    name: str
    value: object

@dataclass
class ArrayLit(Node):
    """`[[1, 2], [3, 4]]`: items are expressions or nested ArrayLit."""
    items: list

@dataclass
class ConstArrayDecl(Node):
    """`const region[2][3] = [[...], [...]];`"""
    name: str
    dims: list
    value: ArrayLit

@dataclass
class EnumDecl(Node):
    """`enum Color = { Red, Green, Blue };`"""
    name: str
    values: list

@dataclass
class VarDecl(Node):
    name: str
    domain: Domain

@dataclass
class ArrayDecl(Node):
    """`array grid[N][N] : 1..N;` (a dim is a size or an enumerated type)."""
    name: str
    dims: list
    domain: Domain

@dataclass
class Constraint(Node):
    expr: object

@dataclass
class RangeLoop(Node):
    """`i in lo..hi`"""
    var: str
    lo: object
    hi: object

@dataclass
class EnumLoop(Node):
    """`c in Color`"""
    var: str
    enum: str

@dataclass
class Forall(Node):
    ranges: list
    body: list


# Expressions

@dataclass
class IntLit(Node):
    value: int

@dataclass
class Var(Node):
    """A name used as a value: x in `constraint x or y;`."""
    name: str

@dataclass
class Slice(Node):
    """The `*` of `grid[i][*]`."""

@dataclass
class Index(Node):
    """`grid[i][j]`, or a slice `grid[i][*]`: indices are expressions/Slice."""
    name: str
    indices: list

@dataclass
class Call(Node):
    """`abs(e)`, `allDifferent(...)`: a function name and its arguments."""
    func: str
    args: list

@dataclass
class Comprehension(Node):
    """`e forall i in 1..N, ... : cond`: sole argument of a global constraint."""
    expr: object
    ranges: list
    cond: object | None

@dataclass
class Neg(Node):
    expr: object

@dataclass
class Arith(Node):
    op: str  # "+", "-", "*"
    left: object
    right: object

@dataclass
class Cmp(Node):
    op: str  # "=", "!=", "<", "<=", ">", ">="
    left: object
    right: object

@dataclass
class And(Node):
    left: object
    right: object

@dataclass
class Or(Node):
    left: object
    right: object

@dataclass
class Not(Node):
    expr: object

@dataclass
class Implies(Node):
    left: object
    right: object


# ------------------------------------------------------------
# Parse tree -> AST
# ------------------------------------------------------------

@v_args(meta=True)
class ASTBuilder(Transformer):
    """
    Turns the Lark parse tree into the AST, bottom-up: Lark calls the method
    named after each rule (or alias) with the meta-information of the node
    (its position) and its children, already transformed, without the
    dropped "..." strings. Tokens (names, integers) are still Token objects
    here (a str subclass): `_name` turns them into plain str.
    """

    @staticmethod
    def _at(node, meta):
        if not meta.empty:
            node.pos = (meta.line, meta.column)
        return node

    @staticmethod
    def _name(token) -> str:
        return str(token)

    # Declarations

    def program(self, meta, items):
        return self._at(Program(items), meta)

    def const_decl(self, meta, items):
        return self._at(ConstDecl(self._name(items[0]), items[1]), meta)

    def const_array_decl(self, meta, items):
        return self._at(ConstArrayDecl(self._name(items[0]), items[1:-1], items[-1]), meta)

    def enum_decl(self, meta, items):
        return self._at(EnumDecl(self._name(items[0]), [self._name(t) for t in items[1:]]), meta)

    def var_decl(self, meta, items):
        return self._at(VarDecl(self._name(items[0]), items[1]), meta)

    def array_decl(self, meta, items):
        return self._at(ArrayDecl(self._name(items[0]), items[1:-1], items[-1]), meta)

    def dim(self, meta, items):
        return items[0]

    def array_lit(self, meta, items):
        return self._at(ArrayLit(items), meta)

    def bool_domain(self, meta, items):
        return self._at(EnumDomain("bool"), meta)

    def range_domain(self, meta, items):
        return self._at(RangeDomain(items[0], items[1]), meta)

    def named_domain(self, meta, items):
        return self._at(EnumDomain(self._name(items[0])), meta)

    # Statements

    def constraint_decl(self, meta, items):
        return self._at(Constraint(items[0]), meta)

    def range_loop(self, meta, items):
        return self._at(RangeLoop(self._name(items[0]), items[1], items[2]), meta)

    def enum_loop(self, meta, items):
        return self._at(EnumLoop(self._name(items[0]), self._name(items[1])), meta)

    def forall_stmt(self, meta, items):
        ranges = [i for i in items if isinstance(i, (RangeLoop, EnumLoop))]
        body = items[len(ranges):]
        return self._at(Forall(ranges, body), meta)

    # Expressions

    def int_lit(self, meta, items):
        return self._at(IntLit(int(items[0])), meta)

    def var_ref(self, meta, items):
        return self._at(Var(self._name(items[0])), meta)

    def index_ref(self, meta, items):
        return self._at(Index(self._name(items[0]), items[1:]), meta)

    def index(self, meta, items):
        return items[0]

    def slice_index(self, meta, items):
        return self._at(Slice(), meta)

    def call(self, meta, items):
        args = []
        if len(items) > 1 and items[1] is not None:
            args = items[1].children if isinstance(items[1], _Args) else [items[1]]
        return self._at(Call(self._name(items[0]), args), meta)

    def comprehension(self, meta, items):
        ranges = [i for i in items[1:] if isinstance(i, (RangeLoop, EnumLoop))]
        cond = items[1 + len(ranges)] if len(items) > 1 + len(ranges) else None
        return self._at(Comprehension(items[0], ranges, cond), meta)

    def args(self, meta, items):
        return _Args(items)

    def neg(self, meta, items):
        return self._at(Neg(items[0]), meta)

    def add(self, meta, items):
        return self._at(Arith("+", items[0], items[1]), meta)

    def sub(self, meta, items):
        return self._at(Arith("-", items[0], items[1]), meta)

    def mul(self, meta, items):
        return self._at(Arith("*", items[0], items[1]), meta)

    def eq(self, meta, items):
        return self._at(Cmp("=", items[0], items[1]), meta)

    def ne(self, meta, items):
        return self._at(Cmp("!=", items[0], items[1]), meta)

    def lt(self, meta, items):
        return self._at(Cmp("<", items[0], items[1]), meta)

    def le(self, meta, items):
        return self._at(Cmp("<=", items[0], items[1]), meta)

    def gt(self, meta, items):
        return self._at(Cmp(">", items[0], items[1]), meta)

    def ge(self, meta, items):
        return self._at(Cmp(">=", items[0], items[1]), meta)

    def and_op(self, meta, items):
        return self._at(And(items[0], items[1]), meta)

    def or_op(self, meta, items):
        return self._at(Or(items[0], items[1]), meta)

    def not_op(self, meta, items):
        return self._at(Not(items[0]), meta)

    def implies(self, meta, items):
        return self._at(Implies(items[0], items[1]), meta)


class _Args:
    """The arguments of a call, wrapped so that `call` can tell them apart."""
    def __init__(self, children):
        self.children = children


_parser = Lark(GRAMMAR, parser="lalr", lexer="basic", propagate_positions=True)

# Readable names for the terminals, for the "expected ..." of syntax errors.
_TERMINAL_TEXT = {t.name: (t.pattern.value if t.pattern.type == "str" else t.name)
                  for t in _parser.terminals}
_TERMINAL_TEXT.update({"NAME": "a name", "INT": "an integer", "$END": "end of file"})


def _describe(terminals) -> str:
    texts = sorted({f"'{_TERMINAL_TEXT[t]}'" if t in _TERMINAL_TEXT and not _TERMINAL_TEXT[t].startswith(("a ", "an ", "end"))
                    else _TERMINAL_TEXT.get(t, t) for t in terminals})
    shown = ", ".join(texts[:8]) + (", ..." if len(texts) > 8 else "")
    return shown


def parse(text: str) -> Program:
    """Parse a whole model; a syntax error raises CompileError with its position."""
    try:
        tree = _parser.parse(text)
    except UnexpectedToken as e:
        found = "end of file" if e.token.type == "$END" else f"'{e.token}'"
        raise CompileError(f"syntax error: unexpected {found}, expected {_describe(e.expected)}",
                           (e.line, e.column)) from None
    except UnexpectedCharacters as e:
        raise CompileError(f"syntax error: unexpected character {e.char!r}", (e.line, e.column)) from None
    except UnexpectedEOF:
        raise CompileError("syntax error: unexpected end of file") from None
    return ASTBuilder().transform(tree)


# ------------------------------------------------------------
# Pretty-printer
# ------------------------------------------------------------
# Shows the structure of the tree: one statement per line, and every
# operator in parentheses, so that the precedences can be read off.

def pretty(node, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(node, Program):
        return "\n".join(["Program"] + [pretty(s, 1) for s in node.statements])
    if isinstance(node, ConstDecl):
        return f"{pad}Const {node.name} = {pretty(node.value)}"
    if isinstance(node, ConstArrayDecl):
        dims = "".join(f"[{pretty(d)}]" for d in node.dims)
        return f"{pad}Const {node.name}{dims} = {pretty(node.value)}"
    if isinstance(node, EnumDecl):
        return f"{pad}Enum {node.name} = {{{', '.join(node.values)}}}"
    if isinstance(node, VarDecl):
        return f"{pad}Var {node.name} : {pretty(node.domain)}"
    if isinstance(node, ArrayDecl):
        dims = "".join(f"[{pretty(d)}]" for d in node.dims)
        return f"{pad}Array {node.name}{dims} : {pretty(node.domain)}"
    if isinstance(node, Constraint):
        return f"{pad}Constraint {pretty(node.expr)}"
    if isinstance(node, Forall):
        head = ", ".join(pretty(r) for r in node.ranges)
        return "\n".join([f"{pad}Forall {head}"] + [pretty(s, indent + 1) for s in node.body])
    if isinstance(node, RangeLoop):
        return f"{node.var} in {pretty(node.lo)}..{pretty(node.hi)}"
    if isinstance(node, EnumLoop):
        return f"{node.var} in {node.enum}"
    if isinstance(node, EnumDomain):
        return node.name
    if isinstance(node, RangeDomain):
        return f"{pretty(node.lo)}..{pretty(node.hi)}"
    if isinstance(node, ArrayLit):
        return "[" + ", ".join(pretty(i) for i in node.items) + "]"
    if isinstance(node, IntLit):
        return str(node.value)
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Slice):
        return "*"
    if isinstance(node, Index):
        return node.name + "".join(f"[{pretty(i)}]" for i in node.indices)
    if isinstance(node, Call):
        return f"{node.func}({', '.join(pretty(a) for a in node.args)})"
    if isinstance(node, Comprehension):
        head = ", ".join(pretty(r) for r in node.ranges)
        cond = f" : {pretty(node.cond)}" if node.cond is not None else ""
        return f"{pretty(node.expr)} forall {head}{cond}"
    if isinstance(node, Neg):
        return f"(-{pretty(node.expr)})"
    if isinstance(node, Not):
        return f"(!{pretty(node.expr)})"
    if isinstance(node, Arith):
        return f"({pretty(node.left)} {node.op} {pretty(node.right)})"
    if isinstance(node, Cmp):
        return f"({pretty(node.left)} {node.op} {pretty(node.right)})"
    if isinstance(node, And):
        return f"({pretty(node.left)} /\\ {pretty(node.right)})"
    if isinstance(node, Or):
        return f"({pretty(node.left)} \\/ {pretty(node.right)})"
    if isinstance(node, Implies):
        return f"({pretty(node.left)} -> {pretty(node.right)})"
    raise TypeError(f"pretty: unexpected node {node!r}")


# ------------------------------------------------------------
# Source printer
# ------------------------------------------------------------
# Prints an AST back as model text, with every operator parenthesised:
# parse(source(ast)) == ast, which the tests check on the examples.

def source(node, indent: int = 0) -> str:
    pad = "    " * indent
    if isinstance(node, Program):
        return "\n".join(source(s) for s in node.statements) + "\n"
    if isinstance(node, ConstDecl):
        return f"{pad}const {node.name} = {source(node.value)};"
    if isinstance(node, ConstArrayDecl):
        dims = "".join(f"[{source(d)}]" for d in node.dims)
        return f"{pad}const {node.name}{dims} = {source(node.value)};"
    if isinstance(node, EnumDecl):
        return f"{pad}enum {node.name} = {{ {', '.join(node.values)} }};"
    if isinstance(node, VarDecl):
        return f"{pad}var {node.name} : {source(node.domain)};"
    if isinstance(node, ArrayDecl):
        dims = "".join(f"[{source(d)}]" for d in node.dims)
        return f"{pad}array {node.name}{dims} : {source(node.domain)};"
    if isinstance(node, Constraint):
        return f"{pad}constraint {source(node.expr)};"
    if isinstance(node, Forall):
        head = ", ".join(source(r) for r in node.ranges)
        body = "\n".join(source(s, indent + 1) for s in node.body)
        return f"{pad}forall {head} {{\n{body}\n{pad}}}"
    if isinstance(node, RangeLoop):
        return f"{node.var} in ({source(node.lo)})..({source(node.hi)})"
    if isinstance(node, EnumLoop):
        return f"{node.var} in {node.enum}"
    if isinstance(node, EnumDomain):
        return node.name
    if isinstance(node, RangeDomain):
        return f"({source(node.lo)})..({source(node.hi)})"
    if isinstance(node, ArrayLit):
        return "[" + ", ".join(source(i) for i in node.items) + "]"
    if isinstance(node, IntLit):
        return str(node.value)
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Slice):
        return "*"
    if isinstance(node, Index):
        return node.name + "".join(f"[{source(i)}]" for i in node.indices)
    if isinstance(node, Call):
        return f"{node.func}({', '.join(source(a) for a in node.args)})"
    if isinstance(node, Comprehension):
        head = ", ".join(source(r) for r in node.ranges)
        cond = f" : {source(node.cond)}" if node.cond is not None else ""
        return f"{source(node.expr)} forall {head}{cond}"
    if isinstance(node, Neg):
        return f"(-{source(node.expr)})"
    if isinstance(node, Not):
        return f"(not {source(node.expr)})"
    if isinstance(node, (Arith, Cmp)):
        return f"({source(node.left)} {node.op} {source(node.right)})"
    if isinstance(node, And):
        return f"({source(node.left)} and {source(node.right)})"
    if isinstance(node, Or):
        return f"({source(node.left)} or {source(node.right)})"
    if isinstance(node, Implies):
        return f"({source(node.left)} -> {source(node.right)})"
    raise TypeError(f"source: unexpected node {node!r}")
