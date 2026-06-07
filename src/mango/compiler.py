from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from mango.expressions import Expr, GroupingElement, and_
from mango.query import (
    FetchClause,
    Join,
    LockingClause,
    Select,
    TableSource,
    WindowDefinition,
    tables_for,
)
from mango.row import row_projection
from mango.sql import (
    SQL,
    ColumnChunk,
    CompiledSql,
    ParamChunk,
    RawChunk,
)

type ParamStyle = Literal["numeric", "pyformat"]


@dataclass(slots=True)
class PostgresCompiler:
    param_style: ParamStyle = "numeric"

    def compile_select[T](self, query: Select[T]) -> CompiledSql:
        params: list[object] = []
        sql = self.compile_select_into(query, params)
        return CompiledSql(sql, tuple(params))

    def compile_select_into[T](self, query: Select[T], params: list[object]) -> str:
        parts: list[str] = []

        if query.with_queries:
            with_prefix = "WITH RECURSIVE" if query.recursive_with else "WITH"
            with_sql = ", ".join(
                self.compile_with_query(with_query, params)
                for with_query in query.with_queries
            )
            parts.append(f"{with_prefix} {with_sql}")

        parts.append(self.compile_select_core(query, params))

        for operation in query.set_operations:
            operation_sql = operation.operator
            if operation.quantifier is not None:
                operation_sql += f" {operation.quantifier}"
            parts.append(
                f"{operation_sql} {self.compile_select_into(operation.query, params)}"
            )

        if query.ordering:
            order_sql = ", ".join(
                self.compile_ordering(item, params) for item in query.ordering
            )
            parts.append(f"ORDER BY {order_sql}")

        if query.limit_value is not None:
            if isinstance(query.limit_value, str):
                parts.append("LIMIT ALL")
            else:
                parts.append(f"LIMIT {self.compile_sql(query.limit_value.sql, params)}")
        if query.offset_value is not None:
            offset = self.compile_sql(query.offset_value.sql, params)
            rows = " ROWS" if query.offset_rows else ""
            parts.append(f"OFFSET {offset}{rows}")

        if query.fetch_clause is not None:
            parts.append(self.compile_fetch(query.fetch_clause, params))

        for locking_clause in query.locking_clauses:
            parts.append(self.compile_locking(locking_clause))

        return " ".join(parts)

    def compile_select_core[T](self, query: Select[T], params: list[object]) -> str:
        projection = row_projection(query.result_type)
        projections = ", ".join(
            f"{self.compile_sql(expression.sql, params)} AS {quote_ident(alias)}"
            for alias, expression in projection.items()
        )
        select_clause = "SELECT"
        if query.quantifier == "ALL":
            select_clause += " ALL"
        elif query.quantifier == "DISTINCT" and query.distinct_on_exprs:
            distinct_on = ", ".join(
                self.compile_sql(expression.sql, params)
                for expression in query.distinct_on_exprs
            )
            select_clause += f" DISTINCT ON ({distinct_on})"
        elif query.quantifier == "DISTINCT":
            select_clause += " DISTINCT"

        parts = [f"{select_clause} {projections}"]
        from_sql = self.compile_from(query, params)
        if from_sql is not None:
            parts.append(f"FROM {from_sql}")

        if query.conditions:
            parts.append(
                f"WHERE {self.compile_sql(and_(*query.conditions).sql, params)}"
            )

        if query.group_by_items:
            quantifier = (
                f"{query.group_by_quantifier} "
                if query.group_by_quantifier is not None
                else ""
            )
            group_sql = ", ".join(
                self.compile_grouping(item, params) for item in query.group_by_items
            )
            parts.append(f"GROUP BY {quantifier}{group_sql}")

        if query.having_conditions:
            parts.append(
                f"HAVING {self.compile_sql(and_(*query.having_conditions).sql, params)}"
            )

        if query.windows:
            window_sql = ", ".join(
                self.compile_window(window, params) for window in query.windows
            )
            parts.append(f"WINDOW {window_sql}")

        return " ".join(parts)

    def compile_sql(self, sql: SQL[Any], params: list[object]) -> str:
        parts: list[str] = []
        for chunk in sql.chunks:
            match chunk:
                case RawChunk(text=text):
                    parts.append(text)
                case ParamChunk(value=value):
                    parts.append(self.add_param(value, params))
                case ColumnChunk(column=column):
                    parts.append(
                        f"{quote_ident(column.table.name)}.{quote_ident(column.name)}"
                    )
                case SQL():
                    parts.append(
                        self.compile_sql(
                            cast(SQL[Any], chunk),  # ty: ignore[redundant-cast]
                            params,
                        )
                    )
                case Select():
                    parts.append(
                        self.compile_select_into(cast(Select[Any], chunk), params)
                    )
                case _:
                    raise TypeError(f"Unsupported SQL chunk: {chunk!r}")
        return "".join(parts)

    def compile_with_query(self, with_query: Any, params: list[object]) -> str:
        columns = (
            f" ({', '.join(quote_ident(column) for column in with_query.columns)})"
            if with_query.columns
            else ""
        )
        materialized = ""
        if with_query.materialized is True:
            materialized = " MATERIALIZED"
        elif with_query.materialized is False:
            materialized = " NOT MATERIALIZED"
        query_sql = self.compile_select_into(with_query.query, params)
        return f"{quote_ident(with_query.name)}{columns} AS{materialized} ({query_sql})"

    def compile_from[T](self, query: Select[T], params: list[object]) -> str | None:
        sources = query.from_items
        if not sources:
            projection = row_projection(query.result_type)
            sources = tuple(
                TableSource(table)
                for table in tables_for(
                    projection.values(),
                    query.conditions,
                    query.ordering,
                    query.group_by_items,
                    query.having_conditions,
                )
            )
        if not sources:
            return None
        from_sql = ", ".join(
            self.compile_table_source(source, params) for source in sources
        )
        if query.joins:
            join_sql = " ".join(self.compile_join(join, params) for join in query.joins)
            return f"{from_sql} {join_sql}"
        return from_sql

    def compile_table_source(self, source: TableSource, params: list[object]) -> str:
        prefix = "ONLY " if source.only else ""
        suffix = " *" if source.include_descendants else ""
        sql = f"{prefix}{quote_ident(source.table.name)}{suffix}"
        if source.sample is not None:
            arguments = ", ".join(
                self.compile_sql(argument.sql, params)
                for argument in source.sample.arguments
            )
            sql += f" TABLESAMPLE {source.sample.method} ({arguments})"
            if source.sample.repeatable is not None:
                repeatable = self.compile_sql(source.sample.repeatable.sql, params)
                sql += f" REPEATABLE ({repeatable})"
        return sql

    def compile_join(self, join: Join, params: list[object]) -> str:
        lateral = "LATERAL " if join.lateral else ""
        target = f"{lateral}{self.compile_table_source(join.target, params)}"
        if join.natural:
            return f"NATURAL {join.kind} JOIN {target}"
        if join.kind == "CROSS":
            return f"CROSS JOIN {target}"

        sql = f"{join.kind} JOIN {target}"
        if join.condition is not None:
            return f"{sql} ON {self.compile_sql(join.condition.sql, params)}"
        using_columns = ", ".join(quote_ident(column) for column in join.using_columns)
        return f"{sql} USING ({using_columns})"

    def compile_grouping(
        self,
        item: Expr[Any] | GroupingElement,
        params: list[object],
    ) -> str:
        if not isinstance(item, GroupingElement):
            return self.compile_sql(item.sql, params)
        if item.kind == "EMPTY":
            return "()"
        inner = ", ".join(self.compile_grouping(child, params) for child in item.items)
        return f"{item.kind} ({inner})"

    def compile_window(
        self,
        window: WindowDefinition,
        params: list[object],
    ) -> str:
        parts: list[str] = []
        if window.partition_by:
            partition_sql = ", ".join(
                self.compile_sql(expression.sql, params)
                for expression in window.partition_by
            )
            parts.append(f"PARTITION BY {partition_sql}")
        if window.order_by:
            order_sql = ", ".join(
                self.compile_ordering(item, params) for item in window.order_by
            )
            parts.append(f"ORDER BY {order_sql}")
        if window.frame is not None:
            parts.append(window.frame)
        return f"{quote_ident(window.name)} AS ({' '.join(parts)})"

    def compile_ordering(self, expression: Expr[Any], params: list[object]) -> str:
        compiled = self.compile_sql(expression.sql, params)
        if compiled.endswith((" ASC", " DESC")):
            return compiled
        return f"{compiled} ASC"

    def compile_fetch(self, fetch: FetchClause, params: list[object]) -> str:
        first = "FIRST" if fetch.first else "NEXT"
        row_word = "ROWS" if fetch.rows else "ROW"
        count = ""
        if fetch.count is not None:
            count = f" {self.compile_sql(fetch.count.sql, params)}"
        mode = "WITH TIES" if fetch.with_ties else "ONLY"
        return f"FETCH {first}{count} {row_word} {mode}"

    def compile_locking(self, locking: LockingClause) -> str:
        sql = f"FOR {locking.strength}"
        if locking.of:
            tables = ", ".join(quote_ident(table.name) for table in locking.of)
            sql += f" OF {tables}"
        if locking.nowait:
            sql += " NOWAIT"
        elif locking.skip_locked:
            sql += " SKIP LOCKED"
        return sql

    def add_param(self, value: object, params: list[object]) -> str:
        params.append(value)
        return self.placeholder(len(params))

    def placeholder(self, index: int) -> str:
        if self.param_style == "numeric":
            return f"${index}"
        return "%s"


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
