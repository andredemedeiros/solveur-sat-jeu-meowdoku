r"""
Syntax of the propositional fragment: grammar (Lark, LALR), AST and
pretty-printer.

    text --(Lark parser)--> parse tree --(ASTBuilder)--> AST

The parse tree is Lark's generic tree (Tree / Token objects, one node per
grammar rule). The AST is made of our own dataclasses (below), one class per
construct of the language, which later passes walk with isinstance.

Example. The text

    var x : bool;
    var y : bool;
    constraint not x and y -> x or y;

gives the AST, as printed by pretty() (`python csp.py model.csp`)

    Program
      Var x : bool
      Var y : bool
      Constraint (((!x) /\ y) -> (x \/ y))
"""

from dataclasses import dataclass
from lark import Transformer, Lark


# Lark notation used in GRAMMAR:
# - "rule: ..." defines a rule; each rule gives a node of the parse tree.
# - "?rule: ...": when the rule has a single child, the child replaces the
#   node. An atom that is a reference is just the reference, no "atom" node.
# - "... -> name" names the node of that alternative, and thus the
#   ASTBuilder method called on it.
# - "..." strings (keywords, punctuation) are matched, then dropped from
#   the tree.
# - NAME is Lark's common.CNAME (identifiers). Whitespace (WS) and //
#   comments (CPP_COMMENT) are skipped with %ignore.
#
# The lexer is "basic" (see `parser` below): it cuts the whole text into
# tokens before parsing, and a keyword ("var", "and", "bool", ...) always
# gives a keyword token, never a NAME. Keywords are thus reserved:
# `var and : bool;` is a syntax error. (Lark's default lexer would decide
# from the context of the parser, and accept it.)

GRAMMAR = r"""
?start: program

program: statement*

?statement: var_decl
          | constraint_decl

// -------------------- STATEMENTS --------------------

// var x : bool;
var_decl: "var" NAME ":" domain ";"

// bool is the only domain of the fragment
domain: "bool"                          -> bool_domain

// constraint x or y;
constraint_decl: "constraint" expr ";"

// -------------------- EXPRESSIONS --------------------
//
// Precedence is encoded by layering the rules, from the loosest to the
// tightest: ->  <  or  <  and  <  not  <  atom
// Each layer either is the next one (the "?" rule is then inlined, no
// node), or combines the next ones with its operator.
//     a or b and c      parses as  a or (b and c)
//     not a and b       parses as  (not a) and b
//     a -> b -> c       parses as  a -> (b -> c)     (right recursive)
//     a or b or c       parses as  (a or b) or c     (left recursive)

?expr: implication

?implication: or_expr
            | or_expr "->" implication  -> implies

?or_expr: and_expr
        | or_expr "or" and_expr         -> or_op

?and_expr: not_expr
         | and_expr "and" not_expr      -> and_op

?not_expr: "not" not_expr               -> not_op
         | atom

?atom: reference
     | "(" expr ")"

?reference: NAME                        -> var_ref

%import common.CNAME -> NAME
%import common.WS
%import common.CPP_COMMENT
%ignore WS
%ignore CPP_COMMENT
"""


# ------------------------------------------------------------
# AST
# ------------------------------------------------------------
# One dataclass per construct (avoids the need for __init__())

# Statements

@dataclass
class Program:
    statements: list

class Domain:
    pass

# "bool" is the boolean domain, the only one of the fragment
@dataclass
class EnumDomain(Domain):
    name: str

@dataclass
class VarDecl:
    name: str
    domain: Domain

@dataclass
class Constraint:
    expr: object


# Expressions

@dataclass
class Var:
    """A name used as a value: x in `constraint x or y;`."""
    name: str

@dataclass
class And:
    left: object
    right: object

@dataclass
class Or:
    left: object
    right: object

@dataclass
class Not:
    expr: object

@dataclass
class Implies:
    left: object
    right: object


class ASTBuilder(Transformer):
    """
    Turns the Lark parse tree into the AST, bottom-up: Lark calls the method
    named after each rule (or alias) of the grammar, with its children
    (items), already transformed, without the dropped "..." strings.
    For "var x : bool;" (rule var_decl), items is ["x", EnumDomain("bool")]:
    NAME() below has already turned the token into a str, and bool_domain()
    the domain into an EnumDomain.

    The value returned replaces the node in its parent's items.
    """

    def program(self, items):
        return Program(items)

    def var_decl(self, items):
        return VarDecl(items[0], items[1])

    def bool_domain(self, items):
        return EnumDomain("bool")

    def constraint_decl(self, items):
        return Constraint(items[0])

    # Expressions

    def NAME(self, items):
        return str(items)

    def var_ref(self, items):
        return Var(items[0])

    def and_op(self, items):
        return And(items[0], items[1])

    def or_op(self, items):
        return Or(items[0], items[1])

    def not_op(self, items):
        return Not(items[0])

    def implies(self, items):
        return Implies(items[0], items[1])


parser = Lark(GRAMMAR, parser="lalr", lexer="basic")


def parse(text: str) -> Program:
    """Parse a whole model."""
    tree = parser.parse(text)
    return ASTBuilder().transform(tree)


# ------------------------------------------------------------
# Pretty-printer
# ------------------------------------------------------------
# Shows the structure of the tree: one statement per line, and every
# binary or unary expression in parentheses, so that the precedences
# chosen by the parser can be read off.

def pretty(node) -> str:
    if isinstance(node, Program):
        return "\n".join(["Program"] + ["  " + pretty(s) for s in node.statements])
    if isinstance(node, VarDecl):
        return f"Var {node.name} : {node.domain.name}"
    if isinstance(node, Constraint):
        return "Constraint " + pretty(node.expr)
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Not):
        return f"(!{pretty(node.expr)})"
    if isinstance(node, And):
        return f"({pretty(node.left)} /\\ {pretty(node.right)})"
    if isinstance(node, Or):
        return f"({pretty(node.left)} \\/ {pretty(node.right)})"
    if isinstance(node, Implies):
        return f"({pretty(node.left)} -> {pretty(node.right)})"
    raise TypeError(f"pretty: unexpected node {node!r}")
