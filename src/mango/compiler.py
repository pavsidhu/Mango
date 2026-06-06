from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from mango.expressions import and_
from mango.query import Select, tables_for
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
        projections = ", ".join(
            f"{self.compile_sql(expression.sql, params)} AS {quote_ident(alias)}"
            for alias, expression in query.projections.items()
        )
        from_tables = tables_for(
            query.projections.values(),
            query.conditions,
            query.ordering,
        )
        from_sql = ", ".join(quote_ident(table.name) for table in from_tables)
        parts = [f"SELECT {projections}", f"FROM {from_sql}"]

        if query.conditions:
            parts.append(
                f"WHERE {self.compile_sql(and_(*query.conditions).sql, params)}"
            )

        if query.ordering:
            order_sql = ", ".join(
                f"{self.compile_sql(item.expression.sql, params)} {item.direction}"
                for item in query.ordering
            )
            parts.append(f"ORDER BY {order_sql}")

        if query.limit_value is not None:
            parts.append(f"LIMIT {self.add_param(query.limit_value, params)}")
        if query.offset_value is not None:
            parts.append(f"OFFSET {self.add_param(query.offset_value, params)}")

        return CompiledSql(" ".join(parts), tuple(params))

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
                case _:
                    raise TypeError(f"Unsupported SQL chunk: {chunk!r}")
        return "".join(parts)

    def add_param(self, value: object, params: list[object]) -> str:
        params.append(value)
        return self.placeholder(len(params))

    def placeholder(self, index: int) -> str:
        if self.param_style == "numeric":
            return f"${index}"
        return "%s"


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
