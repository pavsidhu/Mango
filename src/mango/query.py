from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal, Self, TypeIs, cast

from mango.expressions import Expr, GroupingElement, literal
from mango.projection import hydrate_row
from mango.row import row_projection
from mango.schema import Table
from mango.sql import TableRef

type SelectQuantifier = Literal["ALL", "DISTINCT"]
type JoinKind = Literal["INNER", "LEFT", "RIGHT", "FULL", "CROSS"]
type SetOperator = Literal["UNION", "INTERSECT", "EXCEPT"]
type SetQuantifier = Literal["ALL", "DISTINCT"] | None
type LockStrength = Literal["UPDATE", "NO KEY UPDATE", "SHARE", "KEY SHARE"]
type LockTarget = type[Table] | TableSource
type LockTargets = LockTarget | Iterable[LockTarget] | None


@dataclass(frozen=True, slots=True)
class TableSample:
    method: str
    arguments: tuple[Expr[Any], ...]
    repeatable: Expr[Any] | None = None


@dataclass(frozen=True, slots=True)
class TableSource:
    table: TableRef
    only: bool = False
    include_descendants: bool = False
    sample: TableSample | None = None

    def tablesample(
        self,
        method: str,
        *arguments: object,
        repeatable: object | None = None,
    ) -> Self:
        if not method.isidentifier():
            raise ValueError(f"Invalid TABLESAMPLE method: {method!r}")
        return replace(
            self,
            sample=TableSample(
                method=method,
                arguments=tuple(literal_argument(arg) for arg in arguments),
                repeatable=(
                    None if repeatable is None else literal_argument(repeatable)
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class Join:
    kind: JoinKind
    target: TableSource
    condition: Expr[bool] | None = None
    using_columns: tuple[str, ...] = ()
    natural: bool = False
    lateral: bool = False


@dataclass(frozen=True, slots=True)
class WithQuery:
    name: str
    query: Select[Any]
    columns: tuple[str, ...] = ()
    materialized: bool | None = None


@dataclass(frozen=True, slots=True)
class WindowDefinition:
    name: str
    partition_by: tuple[Expr[Any], ...] = ()
    order_by: tuple[Expr[Any], ...] = ()
    frame: str | None = None


@dataclass(frozen=True, slots=True)
class SetOperation:
    operator: SetOperator
    query: Select[Any]
    quantifier: SetQuantifier = None


@dataclass(frozen=True, slots=True)
class FetchClause:
    count: Expr[Any] | None
    first: bool = True
    rows: bool = True
    with_ties: bool = False


@dataclass(frozen=True, slots=True)
class LockingClause:
    strength: LockStrength
    of: tuple[TableRef, ...] = ()
    nowait: bool = False
    skip_locked: bool = False


@dataclass(frozen=True, slots=True)
class Select[T]:
    result_type: type[T]
    with_queries: tuple[WithQuery, ...] = ()
    recursive_with: bool = False
    quantifier: SelectQuantifier | None = None
    distinct_on_exprs: tuple[Expr[Any], ...] = ()
    from_items: tuple[TableSource, ...] = ()
    joins: tuple[Join, ...] = ()
    conditions: tuple[Expr[bool], ...] = ()
    group_by_items: tuple[Expr[Any] | GroupingElement, ...] = ()
    group_by_quantifier: Literal["ALL", "DISTINCT"] | None = None
    having_conditions: tuple[Expr[bool], ...] = ()
    windows: tuple[WindowDefinition, ...] = ()
    set_operations: tuple[SetOperation, ...] = ()
    ordering: tuple[Expr[Any], ...] = ()
    limit_value: Expr[Any] | Literal["ALL"] | None = None
    offset_value: Expr[Any] | None = None
    offset_rows: bool = False
    fetch_clause: FetchClause | None = None
    locking_clauses: tuple[LockingClause, ...] = ()

    def with_(
        self,
        name: str,
        query: Select[Any],
        *,
        columns: Iterable[str] = (),
        materialized: bool | None = None,
        recursive: bool = False,
    ) -> Select[T]:
        return replace(
            self,
            with_queries=(
                *self.with_queries,
                WithQuery(name, query, tuple(columns), materialized),
            ),
            recursive_with=self.recursive_with or recursive,
        )

    def all_rows(self) -> Select[T]:
        return replace(self, quantifier="ALL", distinct_on_exprs=())

    def distinct(self) -> Select[T]:
        return replace(self, quantifier="DISTINCT", distinct_on_exprs=())

    def distinct_on(self, *expressions: Expr[Any]) -> Select[T]:
        if not expressions:
            raise ValueError("distinct_on() requires at least one expression")
        return replace(
            self,
            quantifier="DISTINCT",
            distinct_on_exprs=expressions,
        )

    def from_(self, *sources: type[Table] | TableSource) -> Select[T]:
        if not sources:
            raise ValueError("from_() requires at least one source")
        return replace(self, from_items=tuple(source_for(source) for source in sources))

    def join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool] | None = None,
        using: Iterable[str] = (),
        kind: JoinKind = "INNER",
        natural: bool = False,
        lateral: bool = False,
    ) -> Select[T]:
        using_columns = tuple(using)
        if kind != "CROSS" and not natural and on is None and not using_columns:
            raise ValueError("join() requires on=, using=, or natural=True")
        if on is not None and using_columns:
            raise ValueError("join() accepts only one of on= or using=")
        return replace(
            self,
            joins=(
                *self.joins,
                Join(
                    kind,
                    source_for(target),
                    condition=on,
                    using_columns=using_columns,
                    natural=natural,
                    lateral=lateral,
                ),
            ),
        )

    def inner_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool] | None = None,
        using: Iterable[str] = (),
    ) -> Select[T]:
        return self.join(target, on=on, using=using, kind="INNER")

    def left_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool] | None = None,
        using: Iterable[str] = (),
    ) -> Select[T]:
        return self.join(target, on=on, using=using, kind="LEFT")

    def right_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool] | None = None,
        using: Iterable[str] = (),
    ) -> Select[T]:
        return self.join(target, on=on, using=using, kind="RIGHT")

    def full_join(
        self,
        target: type[Table] | TableSource,
        *,
        on: Expr[bool] | None = None,
        using: Iterable[str] = (),
    ) -> Select[T]:
        return self.join(target, on=on, using=using, kind="FULL")

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

    def window(
        self,
        name: str,
        *,
        partition_by: Iterable[Expr[Any]] = (),
        order_by: Iterable[Expr[Any]] = (),
        frame: str | None = None,
    ) -> Select[T]:
        return replace(
            self,
            windows=(
                *self.windows,
                WindowDefinition(name, tuple(partition_by), tuple(order_by), frame),
            ),
        )

    def union(self, query: Select[Any]) -> Select[T]:
        return self.set_operation("UNION", query)

    def union_all(self, query: Select[Any]) -> Select[T]:
        return self.set_operation("UNION", query, "ALL")

    def intersect(self, query: Select[Any]) -> Select[T]:
        return self.set_operation("INTERSECT", query)

    def intersect_all(self, query: Select[Any]) -> Select[T]:
        return self.set_operation("INTERSECT", query, "ALL")

    def except_(self, query: Select[Any]) -> Select[T]:
        return self.set_operation("EXCEPT", query)

    def except_all(self, query: Select[Any]) -> Select[T]:
        return self.set_operation("EXCEPT", query, "ALL")

    def set_operation(
        self,
        operator: SetOperator,
        query: Select[Any],
        quantifier: SetQuantifier = None,
    ) -> Select[T]:
        return replace(
            self,
            set_operations=(
                *self.set_operations,
                SetOperation(operator, query, quantifier),
            ),
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

    def fetch(
        self,
        count: int | Expr[Any] | None = None,
        *,
        first: bool = True,
        rows: bool = True,
        with_ties: bool = False,
    ) -> Select[T]:
        if isinstance(count, int) and count < 0:
            raise ValueError("fetch() requires a non-negative count")
        return replace(
            self,
            fetch_clause=FetchClause(
                None if count is None else literal_argument(count),
                first,
                rows,
                with_ties,
            ),
        )

    def for_(
        self,
        strength: LockStrength,
        *,
        of: LockTargets = None,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> Select[T]:
        if nowait and skip_locked:
            raise ValueError("Locking clause accepts only one of nowait or skip_locked")
        return replace(
            self,
            locking_clauses=(
                *self.locking_clauses,
                LockingClause(
                    strength,
                    tuple(table_ref_for(item) for item in normalize_lock_targets(of)),
                    nowait,
                    skip_locked,
                ),
            ),
        )

    def for_update(
        self,
        *,
        of: LockTargets = None,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> Select[T]:
        return self.for_("UPDATE", of=of, nowait=nowait, skip_locked=skip_locked)

    def for_no_key_update(
        self,
        *,
        of: LockTargets = None,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> Select[T]:
        return self.for_(
            "NO KEY UPDATE",
            of=of,
            nowait=nowait,
            skip_locked=skip_locked,
        )

    def for_share(
        self,
        *,
        of: LockTargets = None,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> Select[T]:
        return self.for_("SHARE", of=of, nowait=nowait, skip_locked=skip_locked)

    def for_key_share(
        self,
        *,
        of: LockTargets = None,
        nowait: bool = False,
        skip_locked: bool = False,
    ) -> Select[T]:
        return self.for_(
            "KEY SHARE",
            of=of,
            nowait=nowait,
            skip_locked=skip_locked,
        )

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


def select[T](result_type: type[T]) -> Select[T]:
    row_projection(result_type)
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


def table_ref_for(source: type[Table] | TableSource) -> TableRef:
    return source_for(source).table


def literal_argument(value: object) -> Expr[Any]:
    if isinstance(value, Expr):
        return cast(Expr[Any], value)
    return cast(Expr[Any], literal(value))


def normalize_lock_targets(value: LockTargets) -> tuple[LockTarget, ...]:
    if value is None:
        return ()
    if is_lock_target(value):
        return (value,)
    return tuple(value)


def is_lock_target(value: object) -> TypeIs[LockTarget]:
    return isinstance(value, TableSource) or (
        isinstance(value, type) and issubclass(value, Table)
    )


def tables_for_grouping(item: Expr[Any] | GroupingElement) -> tuple[TableRef, ...]:
    if isinstance(item, Expr):
        return tuple(item.sql.used_tables)

    tables: dict[str, TableRef] = {}
    for child in item.items:
        for table in tables_for_grouping(child):
            tables[table.name] = table
    return tuple(tables.values())
