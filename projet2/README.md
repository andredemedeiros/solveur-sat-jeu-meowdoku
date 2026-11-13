# The propositional fragment of the constraint language

Here is the syntax of the propositional fragment used in the project: the Lark grammar, the construction of the abstract syntax tree (AST), and a pretty-printer.

```
var x : bool;
var y : bool;
var z : bool;

constraint x or y;
constraint (not x) and z;
constraint z -> y;
```

## Quick start

From this folder (needs `lark` 1.0 or later: `pip install lark`):

```bash
python csp.py examples/subject.csp   # print the AST
python -m tests.test_syntax          # tests of the parser (or: pytest)
```

## Files

- `syntax.py` gives the `GRAMMAR` (Lark, LALR), the AST classes, `ASTBuilder` (parse tree to AST), `parse`, `pretty`
- `csp.py` handles the command line
- `examples/` contains files that describe instances to be parsed
- `tests/test_syntax.py` provides some tests

## The fragment

| Construct | Syntax | AST |
|---|---|---|
| Declaration | `var x : bool;` | `VarDecl("x", EnumDomain("bool"))` |
| Constraint | `constraint e;` | `Constraint(e)` |
| Variable | `x` | `Var("x")` |
| Negation | `not e` | `Not(e)` |
| Conjunction | `e1 and e2` | `And(e1, e2)` |
| Disjunction | `e1 or e2` | `Or(e1, e2)` |
| Implication | `e1 -> e2` | `Implies(e1, e2)` |
| Parentheses | `(e)` | `e` itself: no node |

The connectives are, from the tightest to the loosest, `not`, `and`, `or`, `->`.

- `and` and `or` are left associative
- `->` is right associative.

The grammar encodes these rules (via ordering and precedence level):

- `a or b and c` is `Or(a, And(b, c))`,
- `a -> b -> c` is `Implies(a, Implies(b, c))`.

The keywords `var`, `bool`, `constraint`, `not`, `and` and `or` are reserved: `var and : bool;` is a syntax error.

The parser does not check names: `constraint w;` parses even if `w` is not declared.

## The pretty-printer

`pretty(node)` shows the tree. Each statement is on its own line, and every connective is printed with its parentheses. A pretty printer essentially gives you all the tools to understand how to navigate the AST.
