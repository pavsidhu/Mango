from __future__ import annotations

from collections.abc import Generator, Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

from mango.expressions import Expr, GroupingElement, literal
from mango.row import Row, hydrate_row
from mango.schema import Table
from mango.sql import TableRef

type SelectQuantifier = Literal["DISTINCT"]
type JoinKind = Literal["INNER", "LEFT", "RIGHT", "FULL", "CROSS"]


@dataclass(frozen=True, slots=True)
class TableSource:
    table: TableRef
    only: bool = False
    include_descendants: bool = False


@dataclass(frozen=True, slots=True)
class Join:
    kind: JoinKind
    target: TableSource
    condition: Expr[bool] | None = None
    lateral: bool = False


@dataclass(frozen=True, slots=True)
class WithQuery:
    name: str
    query: Select[Any]
    columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Select[T: Row]:
    result_type: type[T]
    with_queries: tuple[WithQuery, ...] = ()
    quantifier: SelectQuantifier | None = None
    from_items: tuple[TableSource, ...] = ()
    joins: tuple[Join, ...] = ()
    conditions: tuple[Expr[bool], ...] = ()
    group_by_items: tuple[Expr[Any] | GroupingElement, ...] = ()
    group_by_quantifier: Literal["ALL", "DISTINCT"] | None = None
    having_conditions: tuple[Expr[bool], ...] = ()
    ordering: tuple[Expr[Any], ...] = ()
    limit_value: Expr[Any] | Literal["ALL"] | None = None
    offset_value: Expr[Any] | None = None
    offset_rows: bool = False

    def with_(
        self,
        name: str,
        query: Select[Any],
        *,
        columns: Iterable[str] = (),
    ) -> Select[T]:
        return replace(
            self,
            with_queries=(
                *self.with_queries,
                WithQuery(name, query, tuple(columns)),
            ),
        )

    def distinct(self) -> Select[T]:
        return replace(self, quantifier="DISTINCT")

    def from_(self, *sources: type[Table] | TableSource) -> Select[T]:
        if not sources:
            raise ValueError("from_() requires at least one source")
        return replace(self, from_items=tuple(source_for(source) for source in sources))

    def join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool] | None = None,
        kind: JoinKind = "INNER",
        lateral: bool = False,
    ) -> Select[T]:
        if kind != "CROSS" and on is None:
            raise ValueError("join() requires on=")
        return replace(
            self,
            joins=(
                *self.joins,
                Join(
                    kind,
                    source_for(target),
                    condition=on,
                    lateral=lateral,
                ),
            ),
        )

    def inner_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool],
    ) -> Select[T]:
        return self.join(target, on=on, kind="INNER")

    def left_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool],
    ) -> Select[T]:
        return self.join(target, on=on, kind="LEFT")

    def right_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool],
    ) -> Select[T]:
        return self.join(target, on=on, kind="RIGHT")

    def full_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool],
    ) -> Select[T]:
        return self.join(target, on=on, kind="FULL")

    def cross_join(self, target: type[Table] | TableSource) -> Select[T]:
        return self.join(target, kind="CROSS")

    def where(self, condition: Expr[bool]) -> Select[T]:
        return replace(self, conditions=(*self.conditions, condition))

    def group_by(
        self,
        *items: Expr[Any] | GroupingElement,
        quantifier: Literal["ALL", "DISTINCT"] | None = None,
    ) -> Select[T]:
        if not items:
            raise ValueError("group_by() requires at least one expression")
        return replace(
            self,
            group_by_items=(*self.group_by_items, *items),
            group_by_quantifier=quantifier or self.group_by_quantifier,
        )

    def having(self, condition: Expr[bool]) -> Select[T]:
        return replace(
            self,
            having_conditions=(*self.having_conditions, condition),
        )

    def order_by(self, *expressions: Expr[Any]) -> Select[T]:
        return replace(self, ordering=(*self.ordering, *expressions))

    def limit(self, value: int | Expr[Any] | Literal["ALL"]) -> Select[T]:
        if isinstance(value, int) and value < 0:
            raise ValueError("limit() requires a non-negative value")
        limit_value = value if isinstance(value, str) else literal_argument(value)
        return replace(self, limit_value=limit_value)

    def offset(self, value: int | Expr[Any], *, rows: bool = False) -> Select[T]:
        if isinstance(value, int) and value < 0:
            raise ValueError("offset() requires a non-negative value")
        return replace(
            self,
            offset_value=literal_argument(value),
            offset_rows=rows,
        )

    def __await__(self) -> Generator[Any, None, list[T]]:
        async def run() -> list[T]:
            from mango.executor import current_executor

            rows = await current_executor().execute(self)
            return [hydrate_row(self.result_type, row) for row in rows]

        return run().__await__()


def select[T: Row](result_type: type[T]) -> Select[T]:
    return Select(result_type=result_type)


def from_table(
    table: type[Table],
    *,
    only: bool = False,
    include_descendants: bool = False,
) -> TableSource:
    return TableSource(
        table.__mango_table__.sql_ref,
        only=only,
        include_descendants=include_descendants,
    )


def tables_for(
    projection_exprs: Iterable[Expr[Any]],
    conditions: tuple[Expr[bool], ...],
    ordering: tuple[Expr[Any], ...],
    group_by_items: tuple[Expr[Any] | GroupingElement, ...] = (),
    having_conditions: tuple[Expr[bool], ...] = (),
) -> tuple[TableRef, ...]:
    tables: dict[str, TableRef] = {}

    for expr in projection_exprs:
        tables.update((table.name, table) for table in expr.sql.used_tables)
    for condition in conditions:
        tables.update((table.name, table) for table in condition.sql.used_tables)
    for item in ordering:
        tables.update((table.name, table) for table in item.sql.used_tables)
    for item in group_by_items:
        for table in tables_for_grouping(item):
            tables[table.name] = table
    for condition in having_conditions:
        tables.update((table.name, table) for table in condition.sql.used_tables)
    return tuple(tables.values())


def source_for(source: type[Table] | TableSource) -> TableSource:
    if isinstance(source, TableSource):
        return source
    return from_table(source)


def literal_argument(value: object) -> Expr[Any]:
    if isinstance(value, Expr):
        return cast(Expr[Any], value)
    return cast(Expr[Any], literal(value))


def tables_for_grouping(item: Expr[Any] | GroupingElement) -> tuple[TableRef, ...]:
    if isinstance(item, Expr):
        return tuple(item.sql.used_tables)

    tables: dict[str, TableRef] = {}
    for child in item.items:
        for table in tables_for_grouping(child):
            tables[table.name] = table
    return tuple(tables.values())
