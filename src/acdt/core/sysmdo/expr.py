"""Expressões aritméticas seguras para métricas derivadas e para o fecho por iteração (sem ``eval``).

Aceita números, nomes (métricas, variáveis de fecho, constantes declaradas), + − × ÷ ** %, parênteses,
comparações não, e as funções ``ceil floor round min max abs sqrt log exp``. Um nome sem valor → ``None``
(desconhecido, nunca zero).
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable, Mapping

_BIN: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
_FN: dict[str, Callable[..., float]] = {
    "ceil": lambda x: float(math.ceil(x)), "floor": lambda x: float(math.floor(x)), "round": lambda x: float(round(x)),
    "min": lambda *a: float(min(a)), "max": lambda *a: float(max(a)), "abs": lambda x: float(abs(x)),
    "sqrt": math.sqrt, "log": math.log, "exp": math.exp}


class ExprError(ValueError):
    pass


def compile_expr(src: str) -> ast.Expression:
    try:
        tree = ast.parse(str(src), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"expressão inválida '{src}': {e.msg}") from e
    for node in ast.walk(tree):
        ok = isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call,
                               ast.USub, ast.UAdd, *tuple(_BIN)))
        if not ok:
            raise ExprError(f"expressão '{src}': elemento não permitido {type(node).__name__}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FN):
            raise ExprError(f"expressão '{src}': só as funções {sorted(_FN)}")
        if isinstance(node, ast.Constant) and (isinstance(node.value, bool) or
                                               not isinstance(node.value, (int, float))):
            raise ExprError(f"expressão '{src}': só constantes numéricas")
    return tree


def names_in(src: str) -> set[str]:
    tree = compile_expr(src)
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - calls


def evaluate(src: str, env: Mapping[str, Any]) -> float | None:
    tree = compile_expr(src)

    def ev(n: ast.AST) -> float | None:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return float(n.value)  # type: ignore[arg-type]  # validado em compile_expr
        if isinstance(n, ast.Name):
            v = env.get(n.id)
            if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                return None
            return float(v)
        if isinstance(n, ast.UnaryOp):
            x = ev(n.operand)
            return None if x is None else (-x if isinstance(n.op, ast.USub) else x)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            if a is None or b is None:
                return None
            try:
                return float(_BIN[type(n.op)](a, b))
            except (ZeroDivisionError, OverflowError, ValueError):
                return None
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            args = [ev(x) for x in n.args]
            if any(a is None for a in args):
                return None
            try:
                return float(_FN[n.func.id](*args))
            except (ValueError, OverflowError):
                return None
        raise ExprError(f"nó não suportado {type(n).__name__}")

    r = ev(tree)
    return r if r is None or math.isfinite(r) else None
