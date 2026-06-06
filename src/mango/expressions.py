from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

from mango.sql import SQL, param, raw


@dataclass(slots=True)
class Expr[T]:
    sql: SQL[T]
    python_type: type[T]

    def asc(self) -> Ordering:
        return Ordering(self, "ASC")

    def desc(self) -> Ordering:
        return Ordering(self, "DESC")

    def __eq__(  # type: ignore[override,reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
        self,
        other: object,
    ) -> Expr[bool]:
        return self._compare("=", other)

    def __ne__(  # type: ignore[override,reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
        self,
        other: object,
    ) -> Expr[bool]:
        return self._compare("<>", other)

    def __lt__(self, other: T | Expr[T]) -> Expr[bool]:
        return self._compare("<", other)

    def __le__(self, other: T | Expr[T]) -> Expr[bool]:
        return self._compare("<=", other)

    def __gt__(self, other: T | Expr[T]) -> Expr[bool]:
        return self._compare(">", other)

    def __ge__(self, other: T | Expr[T]) -> Expr[bool]:
        return self._compare(">=", other)

    def _compare(self, operator: str, other: object) -> Expr[bool]:
        return Expr(
            SQL[bool](
                (
                    raw("("),
                    self.sql,
                    raw(f" {operator} "),
                    ensure_expr(other).sql,
                    raw(")"),
                )
            ),
            bool,
        )


@dataclass(frozen=True, slots=True)
class Ordering:
    expression: Expr[Any]
    direction: Literal["ASC", "DESC"] = "ASC"


def ensure_expr(value: object) -> Expr[Any]:
    if isinstance(value, Expr):
        return cast(Expr[Any], value)
    return Expr(SQL[Any]((param(value),)), type(value))


def and_(*conditions: Expr[bool]) -> Expr[bool]:
    return combine_conditions("AND", conditions, "and_()")


def or_(*conditions: Expr[bool]) -> Expr[bool]:
    return combine_conditions("OR", conditions, "or_()")


def combine_conditions(
    operator: Literal["AND", "OR"],
    conditions: Iterable[Expr[bool]],
    function_name: str,
) -> Expr[bool]:
    iterator = iter(conditions)
    try:
        current = next(iterator)
    except StopIteration as exc:
        raise ValueError(f"{function_name} requires at least one condition") from exc

    for condition in iterator:
        current = Expr(
            SQL[bool](
                (raw("("), current.sql, raw(f" {operator} "), condition.sql, raw(")"))
            ),
            bool,
        )
    return current


def count(expr: Expr[Any]) -> Expr[int]:
    return Expr(SQL[int]((raw("count("), expr.sql, raw(")"))), int)
