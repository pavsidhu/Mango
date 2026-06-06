from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal

from mango.expressions import Expr, Ordering
from mango.projection import hydrate_row, validate_projection
from mango.row import is_row_type, row_projection
from mango.sql import TableRef


@dataclass(frozen=True, slots=True)
class Select[T]:
    result_type: type[T]
    projections: dict[str, Expr[Any]]
    conditions: tuple[Expr[bool], ...] = ()
    ordering: tuple[Ordering, ...] = ()
    limit_value: int | None = None
    offset_value: int | None = None

    def where(self, condition: Expr[bool]) -> Select[T]:
        return replace(self, conditions=(*self.conditions, condition))

    def order_by(
        self,
        *expressions: Expr[Any] | Ordering,
        direction: Literal["ASC", "DESC"] = "ASC",
    ) -> Select[T]:
        ordering = tuple(
            expression
            if isinstance(expression, Ordering)
            else Ordering(expression, direction)
            for expression in expressions
        )
        return replace(self, ordering=(*self.ordering, *ordering))

    def limit(self, value: int) -> Select[T]:
        if value < 0:
            raise ValueError("limit() requires a non-negative value")
        return replace(self, limit_value=value)

    def offset(self, value: int) -> Select[T]:
        if value < 0:
            raise ValueError("offset() requires a non-negative value")
        return replace(self, offset_value=value)

    async def all(self) -> list[T]:
        from mango.executor import current_executor

        rows = await current_executor().fetch_all(self)
        return [hydrate_row(self.result_type, row) for row in rows]

    async def first(self) -> T | None:
        from mango.executor import current_executor

        row = await current_executor().fetch_first(self)
        if row is None:
            return None
        return hydrate_row(self.result_type, row)

    async def one(self) -> T:
        from mango.executor import current_executor

        row = await current_executor().fetch_one(self)
        return hydrate_row(self.result_type, row)


def select[T](result_type: type[T], **projection: Expr[Any]) -> Select[T]:
    selected = (
        row_projection(result_type)
        if not projection and is_row_type(result_type)
        else dict(projection)
    )
    validate_projection(result_type, selected)
    return Select(result_type=result_type, projections=selected)


def tables_for(
    projection_exprs: Iterable[Expr[Any]],
    conditions: tuple[Expr[bool], ...],
    ordering: tuple[Ordering, ...],
) -> tuple[TableRef, ...]:
    tables: dict[str, TableRef] = {}

    for expr in projection_exprs:
        tables.update((table.name, table) for table in expr.sql.used_tables)
    for condition in conditions:
        tables.update((table.name, table) for table in condition.sql.used_tables)
    for item in ordering:
        tables.update((table.name, table) for table in item.expression.sql.used_tables)

    if len(tables) > 1:
        names = ", ".join(sorted(tables))
        raise ValueError(f"This MVP supports only one FROM table, got: {names}")
    if not tables:
        raise ValueError("Select query has no model fields to infer a FROM table")
    return tuple(tables.values())
