from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, cast

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from mango.compiler import PostgresCompiler
from mango.query import Select
from mango.row import Row

_executor: ContextVar[PostgresExecutor | None] = ContextVar(
    "mango_executor",
    default=None,
)


@dataclass(frozen=True, slots=True)
class PostgresExecutor:
    connection: AsyncConnection[Any]
    compiler: PostgresCompiler = dataclass_field(
        default_factory=lambda: PostgresCompiler(param_style="pyformat")
    )

    async def execute[T: Row](self, query: Select[T]) -> list[Mapping[str, Any]]:
        compiled = self.compiler.compile_select(query)
        async with self.connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(cast(Any, compiled.sql), compiled.params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


def bind_executor(executor: PostgresExecutor) -> Token[PostgresExecutor | None]:
    return _executor.set(executor)


def reset_executor(token: Token[PostgresExecutor | None]) -> None:
    _executor.reset(token)


def current_executor() -> PostgresExecutor:
    executor = _executor.get()
    if executor is None:
        raise RuntimeError(
            "No PostgresExecutor is bound. Use `async with connect(...)` "
            "or call `bind_executor()` before executing queries."
        )
    return executor


@asynccontextmanager
async def connect(dsn: str, **kwargs: Any) -> AsyncGenerator[PostgresExecutor]:
    async with await AsyncConnection.connect(dsn, **kwargs) as connection:
        executor = PostgresExecutor(connection)
        token = bind_executor(executor)
        try:
            yield executor
        finally:
            reset_executor(token)
