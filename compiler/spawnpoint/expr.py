"""Rule expressions: a whitelisted subset of Python syntax translated to GDScript.

Supported: numbers, strings, true/false, `score`, `lives`, `time`, `vars.<name>`,
`event.<arg>`, `self`, `self.<Component>.<property>`, functions count("Entity"), randf(),
min, max, abs, str; operators + - * / %, comparisons (chainable), and/or/not.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field

from .diagnostics import Diagnostics, did_you_mean
from .manifest import Manifest

FUNCS = {"count": (1, 1), "randf": (0, 0), "min": (2, 2), "max": (2, 2), "abs": (1, 1), "str": (1, 1)}
GLOBALS = {"score": "GameState.score", "lives": "GameState.lives", "time": "GameState.time"}
CONSTS = {"true": "true", "false": "false", "True": "true", "False": "false", "null": "null", "None": "null"}

_BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}
_CMP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}


class ExprError(Exception):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


@dataclass
class Scope:
    """What an expression may reference."""

    manifest: Manifest
    entities: dict[str, list[str]]  # entity name -> component names
    event_args: dict[str, str] = field(default_factory=dict)  # arg name -> GDScript param name
    self_entity: str | None = None  # entity type of `self`, None if no source entity
    used: set[str] = field(default_factory=set)  # param names referenced (for unused-arg naming)


_STRING = re.compile(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')")


def normalize(src: str) -> str:
    """Accept common C-style operators from LLM output (outside string literals)."""
    parts = _STRING.split(src)
    for i in range(0, len(parts), 2):
        s = parts[i].replace("&&", " and ").replace("||", " or ")
        parts[i] = re.sub(r"!(?!=)", " not ", s)
    return "".join(parts)


def parse(src: str) -> ast.expr:
    try:
        return ast.parse(normalize(src).strip(), mode="eval").body
    except SyntaxError as e:
        raise ExprError(f"syntax error in '{src}': {e.msg}") from e


def translate(src: str, scope: Scope) -> str:
    return _Translator(scope).visit(parse(src))


def check(src: str, scope: Scope, diags: Diagnostics, path: str) -> str | None:
    try:
        return translate(src, scope)
    except ExprError as e:
        diags.error("E_EXPR", path, str(e), e.hint)
        return None


def gd_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


class _Translator:
    def __init__(self, scope: Scope):
        self.s = scope

    def visit(self, node: ast.AST) -> str:
        method = getattr(self, "v_" + type(node).__name__, None)
        if method is None:
            raise ExprError(f"'{ast.unparse(node)}' is not allowed in rule expressions")
        return method(node)

    def v_Constant(self, n: ast.Constant) -> str:
        v = n.value
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return "null"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return gd_string(v)
        raise ExprError(f"unsupported literal {v!r}")

    def v_Name(self, n: ast.Name) -> str:
        if n.id in CONSTS:
            return CONSTS[n.id]
        if n.id in GLOBALS:
            return GLOBALS[n.id]
        if n.id == "self":
            if self.s.self_entity is None:
                raise ExprError("'self' is not available for this event (no emitting entity)")
            self.s.used.add("source")
            return "source"
        if n.id in self.s.entities:
            raise ExprError(f"'{n.id}' is an entity type, not a value", f'Use count("{n.id}") for how many exist')
        if n.id in ("event", "vars"):
            raise ExprError(f"'{n.id}' needs a field, e.g. {n.id}.something")
        raise ExprError(f"unknown name '{n.id}'", did_you_mean(n.id, [*GLOBALS, "self", "event", "vars"]))

    def v_Attribute(self, n: ast.Attribute) -> str:
        chain = _attr_chain(n)
        if chain is None:
            raise ExprError(f"'{ast.unparse(n)}' is not allowed")
        head, *rest = chain
        if head == "vars" and len(rest) == 1:
            return f"GameState.get_var({gd_string(rest[0])})"
        if head == "event" and len(rest) == 1:
            arg = rest[0]
            if arg not in self.s.event_args:
                opts = list(self.s.event_args)
                raise ExprError(f"event has no argument '{arg}'",
                                did_you_mean(arg, opts) if opts else "This event has no arguments")
            gd = self.s.event_args[arg]
            self.s.used.add(gd)
            return gd
        if head == "self" and len(rest) == 2:
            if self.s.self_entity is None:
                raise ExprError("'self' is not available for this event (no emitting entity)")
            comp_name, prop = rest
            comps = self.s.entities.get(self.s.self_entity, [])
            if comp_name not in comps:
                raise ExprError(f"{self.s.self_entity} has no component '{comp_name}'", did_you_mean(comp_name, comps))
            comp = self.s.manifest.get(comp_name)
            props = [*comp.params, *comp.state] if comp else []
            if prop not in props:
                raise ExprError(f"{comp_name} has no property '{prop}'", did_you_mean(prop, props))
            self.s.used.add("source")
            return f'SP.component(source, &"{comp_name}").{prop}'
        raise ExprError(f"'{ast.unparse(n)}' is not allowed",
                        "Use vars.<name>, event.<arg> or self.<Component>.<property>")

    def v_Call(self, n: ast.Call) -> str:
        if not isinstance(n.func, ast.Name) or n.func.id not in FUNCS:
            name = ast.unparse(n.func)
            raise ExprError(f"function '{name}' is not allowed in expressions", did_you_mean(name, FUNCS))
        if n.keywords:
            raise ExprError("keyword arguments are not supported")
        lo, hi = FUNCS[n.func.id]
        if not lo <= len(n.args) <= hi:
            raise ExprError(f"{n.func.id}() takes {lo if lo == hi else f'{lo}-{hi}'} argument(s), got {len(n.args)}")
        if n.func.id == "count":
            name = entity_literal(n.args[0], self.s.entities)
            return f'World.count(&"{name}")'
        args = ", ".join(self.visit(a) for a in n.args)
        return f"{n.func.id}({args})"

    def v_BinOp(self, n: ast.BinOp) -> str:
        a, b = self.visit(n.left), self.visit(n.right)
        if isinstance(n.op, ast.Div):
            return f"(float({a}) / {b})"
        if isinstance(n.op, ast.Mod):
            return f"fposmod({a}, {b})"
        op = _BIN.get(type(n.op))
        if op is None:
            raise ExprError(f"operator in '{ast.unparse(n)}' is not supported")
        return f"({a} {op} {b})"

    def v_UnaryOp(self, n: ast.UnaryOp) -> str:
        v = self.visit(n.operand)
        if isinstance(n.op, ast.Not):
            return f"(not {v})"
        if isinstance(n.op, ast.USub):
            return f"(-{v})"
        if isinstance(n.op, ast.UAdd):
            return v
        raise ExprError(f"operator in '{ast.unparse(n)}' is not supported")

    def v_BoolOp(self, n: ast.BoolOp) -> str:
        op = " and " if isinstance(n.op, ast.And) else " or "
        return "(" + op.join(self.visit(v) for v in n.values) + ")"

    def v_Compare(self, n: ast.Compare) -> str:
        parts = []
        left = n.left
        for op, right in zip(n.ops, n.comparators):
            sym = _CMP.get(type(op))
            if sym is None:
                raise ExprError(f"comparison in '{ast.unparse(n)}' is not supported")
            parts.append(f"{self.visit(left)} {sym} {self.visit(right)}")
            left = right
        return "(" + " and ".join(parts) + ")"


def _attr_chain(n: ast.AST) -> list[str] | None:
    out: list[str] = []
    while isinstance(n, ast.Attribute):
        out.append(n.attr)
        n = n.value
    if not isinstance(n, ast.Name):
        return None
    out.append(n.id)
    return out[::-1]


def entity_literal(node: ast.AST, entities: dict[str, list[str]]) -> str:
    """An argument that must be a string literal naming an entity type."""
    if isinstance(node, ast.Name) and node.id in entities:
        return node.id  # be lenient: count(Slime) == count("Slime")
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        raise ExprError(f"expected an entity name in quotes, got '{ast.unparse(node)}'")
    if node.value not in entities:
        raise ExprError(f"unknown entity '{node.value}'", did_you_mean(node.value, entities))
    return node.value
