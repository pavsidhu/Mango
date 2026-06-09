from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from mango.expressions import Expr, GroupingElement, and_
from mango.query import Join, Select, TableSource, tables_for
from mango.row import Row, row_projection
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

    def compile_select[T: Row](self, query: Select[T]) -> CompiledSql:
        params: list[object] = []
        sql = self.compile_select_into(query, params)
        return CompiledSql(sql, tuple(params))

    def compile_select_into[T: Row](
        self, query: Select[T], params: list[object]
    ) -> str:
        parts: list[str] = []

        if query.with_queries:
            with_sql = ", ".join(
                self.compile_with_query(with_query, params)
                for with_query in query.with_queries
            )
            parts.append(f"WITH {with_sql}")

        parts.append(self.compile_select_core(query, params))

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

        return " ".join(parts)

    def compile_select_core[T: Row](
        self, query: Select[T], params: list[object]
    ) -> str:
        projection = row_projection(query.result_type)
        projections = ", ".join(
            f"{self.compile_sql(expression.sql, params)} AS {quote_ident(alias)}"
            for alias, expression in projection.items()
        )
        select_clause = "SELECT"
        if query.quantifier == "DISTINCT":
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
        query_sql = self.compile_select_into(with_query.query, params)
        return f"{quote_ident(with_query.name)}{columns} AS ({query_sql})"

    def compile_from[T: Row](
        self, query: Select[T], params: list[object]
    ) -> str | None:
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
        return f"{prefix}{quote_ident(source.table.name)}{suffix}"

    def compile_join(self, join: Join, params: list[object]) -> str:
        lateral = "LATERAL " if join.lateral else ""
        target = f"{lateral}{self.compile_table_source(join.target, params)}"
        if join.kind == "CROSS":
            return f"CROSS JOIN {target}"

        if join.condition is None:
            raise ValueError(f"{join.kind} JOIN requires an ON condition")
        sql = f"{join.kind} JOIN {target}"
        return f"{sql} ON {self.compile_sql(join.condition.sql, params)}"

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

    def compile_ordering(self, expression: Expr[Any], params: list[object]) -> str:
        compiled = self.compile_sql(expression.sql, params)
        if compiled.endswith((" ASC", " DESC")):
            return compiled
        return f"{compiled} ASC"

    def add_param(self, value: object, params: list[object]) -> str:
        params.append(value)
        return self.placeholder(len(params))

    def placeholder(self, index: int) -> str:
        if self.param_style == "numeric":
            return f"${index}"
        return "%s"


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
