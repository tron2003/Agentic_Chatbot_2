"""Safe calculator and current date/time tools.

LLMs are unreliable at arithmetic and don't know today's date; these two tiny
tools fix both. The calculator walks the AST and only allows numbers and
arithmetic operators, so it can't execute code.
"""

from __future__ import annotations

import ast
import math
import operator
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool

_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp, "abs": abs, "round": round,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "floor": math.floor, "ceil": math.ceil,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expression: str) -> float | int:
    expression = expression.replace("^", "**").replace("×", "*").replace(",", "")
    if len(expression) > 300:
        raise ValueError("Expression too long")

    def ev(node: ast.AST):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Exponent too large")
            return _BIN[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError(f"Unsupported expression element: {ast.dump(node)[:60]}")

    return ev(ast.parse(expression.strip(), mode="eval"))


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression exactly, e.g. "(1250 * 0.18) + 42" or "sqrt(2) ** 3".
    Supports + - * / // % ** and sqrt, log, log10, exp, abs, round, sin, cos, tan, floor, ceil, pi, e."""
    try:
        result = safe_eval(expression)
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as exc:
        return f"Error: {exc}"
    if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
        result = int(result)
    return f"{expression} = {result}"


@tool
def current_datetime(timezone: str = "UTC") -> str:
    """Return the current date and time. Optionally pass an IANA timezone such as "Asia/Kolkata" or "America/New_York"."""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
        timezone = "UTC"
    now = datetime.now(tz)
    return f"{now:%A, %d %B %Y, %H:%M} ({timezone}, ISO {now.isoformat(timespec='seconds')})"
