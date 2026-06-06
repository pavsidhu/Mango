from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any


@dataclass(frozen=True, slots=True)
class TableRef:
    name: str


@dataclass(frozen=True, slots=True)
class ColumnRef:
    table: TableRef
    name: str


@dataclass(frozen=True, slots=True)
class RawChunk:
    text: str


@dataclass(frozen=True, slots=True)
class ParamChunk:
    value: object


@dataclass(frozen=True, slots=True)
class ColumnChunk:
    column: ColumnRef


@dataclass(frozen=True, slots=True)
class SQL[T]:
    chunks: tuple[object, ...] = ()
    used_tables: frozenset[TableRef] = dataclass_field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "used_tables", collect_used_tables(self.chunks))


@dataclass(frozen=True, slots=True)
class CompiledSql:
    sql: str
    params: tuple[Any, ...]


def raw(text: str) -> RawChunk:
    return RawChunk(text)


def param(value: object) -> ParamChunk:
    return ParamChunk(value)


def column_sql(table_ref: TableRef, name: str) -> SQL[Any]:
    return SQL((ColumnChunk(ColumnRef(table_ref, name)),))


def collect_used_tables(chunks: tuple[object, ...]) -> frozenset[TableRef]:
    tables: set[TableRef] = set()
    for chunk in chunks:
        match chunk:
            case ColumnChunk(column=ColumnRef(table=table_ref)) if table_ref.name:
                tables.add(table_ref)
            case SQL(used_tables=used_tables):
                tables.update(used_tables)
            case _:
                pass
    return frozenset(tables)
