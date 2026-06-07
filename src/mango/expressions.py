from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Self, cast

from mango.sql import SQL, ParamChunk, RawChunk


@dataclass(frozen=True, slots=True)
class GroupingElement:
    kind: str
    items: tuple[Expr[Any] | GroupingElement, ...] = ()


@dataclass(slots=True)
class Expr[T]:
    sql: SQL[T]
    python_type: type[T]

    def asc(self) -> Expr[T]:
        return Expr(
            SQL[T]((self.sql, RawChunk(" ASC"))),
            self.python_type,
        )

    def desc(self) -> Expr[T]:
        return Expr(
            SQL[T]((self.sql, RawChunk(" DESC"))),
            self.python_type,
        )

    def is_null(self) -> Expr[bool]:
        return postfix_expr(self, "IS NULL")

    def is_not_null(self) -> Expr[bool]:
        return postfix_expr(self, "IS NOT NULL")

    def in_(self, values: Iterable[object]) -> Expr[bool]:
        return in_expr(self, "IN", values)

    def not_in(self, values: Iterable[object]) -> Expr[bool]:
        return in_expr(self, "NOT IN", values)

    def like(self, pattern: object) -> Expr[bool]:
        return compare_expr(self, "LIKE", pattern)

    def not_like(self, pattern: object) -> Expr[bool]:
        return compare_expr(self, "NOT LIKE", pattern)

    def ilike(self, pattern: object) -> Expr[bool]:
        return compare_expr(self, "ILIKE", pattern)

    def not_ilike(self, pattern: object) -> Expr[bool]:
        return compare_expr(self, "NOT ILIKE", pattern)

    def __add__(self, other: object) -> Expr[T]:
        return arithmetic_expr(self, "+", other)

    def __sub__(self, other: object) -> Expr[T]:
        return arithmetic_expr(self, "-", other)

    def __mul__(self, other: object) -> Expr[T]:
        return arithmetic_expr(self, "*", other)

    def __truediv__(self, other: object) -> Expr[T]:
        return arithmetic_expr(self, "/", other)

    def __eq__(  # type: ignore[override,reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
        self,
        other: object,
    ) -> Expr[bool]:
        return compare_expr(self, "=", other)

    def __ne__(  # type: ignore[override,reportIncompatibleMethodOverride]  # ty: ignore[invalid-method-override]
        self,
        other: object,
    ) -> Expr[bool]:
        return compare_expr(self, "<>", other)

    def __lt__(self, other: T | Expr[T]) -> Expr[bool]:
        return compare_expr(self, "<", other)

    def __le__(self, other: T | Expr[T]) -> Expr[bool]:
        return compare_expr(self, "<=", other)

    def __gt__(self, other: T | Expr[T]) -> Expr[bool]:
        return compare_expr(self, ">", other)

    def __ge__(self, other: T | Expr[T]) -> Expr[bool]:
        return compare_expr(self, ">=", other)


def compare_expr(left: Expr[Any], operator: str, other: object) -> Expr[bool]:
    return Expr(
        SQL[bool](
            (
                RawChunk("("),
                left.sql,
                RawChunk(f" {operator} "),
                ensure_expr(other).sql,
                RawChunk(")"),
            )
        ),
        bool,
    )


def postfix_expr(left: Expr[Any], operator: str) -> Expr[bool]:
    return Expr(SQL[bool]((RawChunk("("), left.sql, RawChunk(f" {operator})"))), bool)


def arithmetic_expr[T](left: Expr[T], operator: str, other: object) -> Expr[T]:
    return Expr(
        SQL[T](
            (
                RawChunk("("),
                left.sql,
                RawChunk(f" {operator} "),
                ensure_expr(other).sql,
                RawChunk(")"),
            )
        ),
        left.python_type,
    )


def in_expr(left: Expr[Any], operator: str, values: Iterable[object]) -> Expr[bool]:
    exprs = tuple(ensure_expr(value) for value in values)
    if not exprs:
        raise ValueError(f"{operator} requires at least one value")

    chunks: list[object] = [RawChunk("("), left.sql, RawChunk(f" {operator} (")]
    for index, expr in enumerate(exprs):
        if index:
            chunks.append(RawChunk(", "))
        chunks.append(expr.sql)
    chunks.extend((RawChunk("))"),))
    return Expr(SQL[bool](tuple(chunks)), bool)


def ensure_expr(value: object) -> Expr[Any]:
    if isinstance(value, Expr):
        return cast(Expr[Any], value)
    return Expr(SQL[Any]((ParamChunk(value),)), type(value))


def literal[T](value: T) -> Expr[T]:
    return Expr(SQL[T]((ParamChunk(value),)), type(value))


def raw_expr[T](text: str, python_type: type[T]) -> Expr[T]:
    return Expr(SQL[T]((RawChunk(text),)), python_type)


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
                (
                    RawChunk("("),
                    current.sql,
                    RawChunk(f" {operator} "),
                    condition.sql,
                    RawChunk(")"),
                )
            ),
            bool,
        )
    return current


def not_(condition: Expr[bool]) -> Expr[bool]:
    return Expr(SQL[bool]((RawChunk("(NOT "), condition.sql, RawChunk(")"))), bool)


def func[T](name: str, return_type: type[T], *arguments: object) -> Expr[T]:
    validate_sql_name(name, "function name")
    chunks: list[object] = [RawChunk(f"{name}(")]
    for index, argument in enumerate(arguments):
        if index:
            chunks.append(RawChunk(", "))
        chunks.append(ensure_expr(argument).sql)
    chunks.append(RawChunk(")"))
    return Expr(SQL[T](tuple(chunks)), return_type)


def count(expr: Expr[Any] | None = None) -> Expr[int]:
    if expr is None:
        return Expr(SQL[int]((RawChunk("count(*)"),)), int)
    return Expr(SQL[int]((RawChunk("count("), expr.sql, RawChunk(")"))), int)


class CaseBuilder[T]:
    def __init__(self, return_type: type[T]) -> None:
        self.return_type = return_type
        self.whens: tuple[tuple[Expr[bool], object], ...] = ()

    def when(self, condition: Expr[bool], value: object) -> Self:
        self.whens = (*self.whens, (condition, value))
        return self

    def else_(self, value: object) -> Expr[T]:
        if not self.whens:
            raise ValueError("case() requires at least one when() clause")

        chunks: list[object] = [RawChunk("CASE")]
        for condition, result in self.whens:
            chunks.extend(
                (
                    RawChunk(" WHEN "),
                    condition.sql,
                    RawChunk(" THEN "),
                    ensure_expr(result).sql,
                )
            )
        chunks.extend((RawChunk(" ELSE "), ensure_expr(value).sql, RawChunk(" END")))
        return Expr(SQL[T](tuple(chunks)), self.return_type)


def case[T](return_type: type[T]) -> CaseBuilder[T]:
    return CaseBuilder(return_type)


def exists(query: object) -> Expr[bool]:
    return Expr(SQL[bool]((RawChunk("EXISTS ("), query, RawChunk(")"))), bool)


def validate_sql_name(value: str, description: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*", value):
        raise ValueError(f"Invalid {description}: {value!r}")
