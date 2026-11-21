"""
Fixed grammar for runtime policy conditions (CE-SEC-003). Replaces eval().

A condition is parsed with Python's `ast` module and then walked against an explicit
allow-list of node types. Nothing is ever compiled or executed. Allowed:

- names: a document field name (letters, digits, underscore; no leading underscore),
  or the literals True, False, None
- literals: strings, numbers, booleans, None, and lists or tuples of those
- comparisons: ==, !=, <, <=, >, >=, in, not in, is, is not (chains allowed)
  Identity comparisons require a right-hand None, True or False literal. A
  comparison that cannot be evaluated raises PolicyExpressionError.
- boolean logic: and, or, not, parentheses; unary minus on a number
- two helper calls, each with one string literal argument:
  is_field_changed('<field>') and has_role('<role>')

Everything else (attribute access, subscripts, other calls, arithmetic, lambdas,
comprehensions, f-strings, dunder names) is rejected with PolicyExpressionError when the
policy is registered, and again when it is evaluated.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Callable, List, Optional

MAX_EXPRESSION_LENGTH = 1000
_FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_HELPERS = ("is_field_changed", "has_role")
_COMPARATORS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)


class PolicyExpressionError(ValueError):
    """The condition is not in the allowed grammar, or could not be evaluated safely."""


def _check_literal(node: ast.AST) -> None:
    if isinstance(node, ast.Constant):
        if node.value is None or isinstance(node.value, (bool, int, float, str)):
            return
        raise PolicyExpressionError("Only string, number, boolean and None literals are allowed")
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, (ast.List, ast.Tuple)):
                raise PolicyExpressionError("Nested lists are not allowed")
            _check_literal(elt)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) \
            and isinstance(node.operand.value, (int, float)) and not isinstance(node.operand.value, bool):
        return
    raise PolicyExpressionError(f"Not a literal: {type(node).__name__}")


def _check(node: ast.AST) -> None:
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise PolicyExpressionError("Only 'and' and 'or' are allowed")
        for value in node.values:
            _check(value)
        return
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            _check(node.operand)
            return
        _check_literal(node)
        return
    if isinstance(node, ast.Compare):
        _check_operand(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            if not isinstance(op, _COMPARATORS):
                raise PolicyExpressionError(f"Comparison {type(op).__name__} is not allowed")
            if isinstance(op, (ast.Is, ast.IsNot)) and not (
                isinstance(comparator, ast.Constant)
                and (comparator.value is None or isinstance(comparator.value, bool))
            ):
                raise PolicyExpressionError("'is' and 'is not' require a None, True or False literal")
            _check_operand(comparator)
        return
    _check_operand(node)


def _check_operand(node: ast.AST) -> None:
    if isinstance(node, ast.Name):
        if not _FIELD_NAME.match(node.id) or node.id in _HELPERS:
            raise PolicyExpressionError(f"Name '{node.id}' is not an allowed field name")
        return
    if isinstance(node, ast.Call):
        if not (isinstance(node.func, ast.Name) and node.func.id in _HELPERS):
            raise PolicyExpressionError("Only is_field_changed() and has_role() may be called")
        if node.keywords or len(node.args) != 1 or not (
            isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        ):
            raise PolicyExpressionError(f"{node.func.id}() takes exactly one string literal")
        return
    if isinstance(node, (ast.BoolOp, ast.Compare)) or (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
        _check(node)
        return
    _check_literal(node)


def parse_condition(expr: str) -> ast.Expression:
    """Parse and validate a condition. Raises PolicyExpressionError if it is not allowed."""
    if not isinstance(expr, str) or not expr.strip():
        raise PolicyExpressionError("Condition must be a non-empty string")
    if len(expr) > MAX_EXPRESSION_LENGTH:
        raise PolicyExpressionError("Condition is too long")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise PolicyExpressionError(f"Condition is not valid syntax: {exc.msg}") from exc
    _check(tree.body)
    return tree


def _literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(e) for e in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -node.operand.value
    raise PolicyExpressionError(f"Not a literal: {type(node).__name__}")


def _compare(op: ast.cmpop, left: Any, right: Any) -> bool:
    try:
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
    except TypeError as exc:
        raise PolicyExpressionError(f"Comparison {type(op).__name__} could not be evaluated") from exc
    raise PolicyExpressionError(f"Comparison {type(op).__name__} is not allowed")


def evaluate_condition(
    expr: str,
    get_field: Callable[[str], Any],
    is_field_changed: Callable[[str], bool],
    has_role: Callable[[str], bool],
) -> bool:
    """Evaluate a validated condition. Raises PolicyExpressionError on anything unexpected."""
    tree = parse_condition(expr)

    def value(node: ast.AST) -> Any:
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(bool(value(v)) for v in node.values)
            return any(bool(value(v)) for v in node.values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not bool(value(node.operand))
        if isinstance(node, ast.Compare):
            left = value(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = value(comparator)
                if not _compare(op, left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Name):
            return get_field(node.id)
        if isinstance(node, ast.Call):
            arg = node.args[0].value
            return bool(is_field_changed(arg)) if node.func.id == "is_field_changed" else bool(has_role(arg))
        return _literal(node)

    return bool(value(tree.body))


def condition_field_names(expr: str) -> List[str]:
    """Field names a condition reads (for review and audit)."""
    tree = parse_condition(expr)
    return sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in _HELPERS})


def validate_condition(expr: Optional[str]) -> None:
    """Registration-time check. None or empty means no condition."""
    if expr is None or (isinstance(expr, str) and not expr.strip()):
        return
    parse_condition(expr)
