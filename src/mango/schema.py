"""Table and column definitions"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, ClassVar, cast, overload

from mango.expressions import Expr
from mango.sql import SQL, ColumnChunk, ColumnRef, TableRef


@dataclass(frozen=True, slots=True)
class TableMetadata:
    """Runtime metadata for a declared table (name, columns, SQL reference)."""

    name: str
    columns: dict[str, Column[Any]]
    sql_ref: TableRef = dataclass_field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sql_ref", TableRef(self.name))


class Column[T](Expr[T]):
    """One table column: Python type, SQL type, and query expression.

    Columns are descriptors. Access on the owning :class:`Table` class returns
    the column (for ``User.age > 18``); access on a row instance returns the
    stored value`.
    """

    python_type: type[T]
    sql_type: str
    column_name: str
    table: TableMetadata | None
    primary_key: bool

    def __init__(
        self,
        python_type: type[T],
        *,
        sql_type: str,
        column_name: str | None = None,
        primary_key: bool = False,
    ) -> None:
        self.python_type = python_type
        self.sql_type = sql_type
        self.column_name = column_name or ""
        self.table = None
        self.primary_key = primary_key
        super().__init__(
            SQL((ColumnChunk(ColumnRef(TableRef(""), self.column_name)),)),
            python_type,
        )

    def bind(self, table: TableMetadata, attr_name: str) -> None:
        """Attach this column to a table after the class body is evaluated."""
        column_name = self.column_name or attr_name
        object.__setattr__(self, "column_name", column_name)
        object.__setattr__(self, "table", table)
        object.__setattr__(
            self,
            "sql",
            SQL((ColumnChunk(ColumnRef(table.sql_ref, column_name)),)),
        )

    @overload
    def __get__(self, instance: None, owner: type[Table]) -> Column[T]: ...

    @overload
    def __get__(self, instance: Table, owner: type[Table]) -> T: ...

    def __get__(self, instance: Table | None, owner: type[Table]) -> Column[T] | T:
        if instance is None:
            return self

        storage = cast(dict[str, Any], object.__getattribute__(instance, "__dict__"))
        return storage[self.column_name]

    def __set__(self, instance: Table, value: T) -> None:
        storage = cast(dict[str, Any], object.__getattribute__(instance, "__dict__"))
        storage[self.column_name] = value


class TableMeta(type):
    """Collects :class:`Column` attributes when a :class:`Table` subclass is defined."""

    def __new__(
        cls,
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        # Runs when Python executes `class User(Table): ...` — before any
        # User() instances exist. Builds the class object and attaches table metadata.
        created: Any = super().__new__(cls, name, bases, namespace, **kwargs)

        # The bare `Table` base class has no columns; only subclasses get registered.
        if name == "Table" and created.__module__ == __name__:
            return created

        # Columns from parent table classes (e.g. a mixin or base table).
        inherited: dict[str, Column[Any]] = {}
        for base in bases:
            inherited.update(getattr(base, "__mango_columns__", {}))

        # Columns declared on this class body (e.g. `name = varchar()`).
        own_columns: dict[str, Column[Any]] = {
            attr_name: value
            for attr_name, value in namespace.items()
            if isinstance(value, Column)
        }
        columns: dict[str, Column[Any]] = {**inherited, **own_columns}

        # SQL table name: explicit __tablename__ or snake_case of the class name.
        table_name = namespace.get("__tablename__", to_snake_case(name))
        metadata = TableMetadata(table_name, columns)

        # Wire each column back to this table (SQL ref, column name, etc.).
        for attr_name, column_obj in columns.items():
            column_obj.bind(metadata, attr_name)

        # Stash on the class so query compilation can read table/column info later.
        created.__mango_table__ = metadata
        created.__mango_columns__ = columns

        return created


class Table(metaclass=TableMeta):
    """Base class for ORM table definitions.

    Example::

        class User(Table):
            __tablename__ = "users"  # optional; defaults to snake_case class name
            name = varchar()
            age = integer()

    After definition, ``User.__mango_table__`` holds :class:`TableMetadata` and
    ``User.__mango_columns__`` maps attribute names to :class:`Column` objects.
    """

    __tablename__: ClassVar[str]
    __mango_table__: ClassVar[TableMetadata]
    __mango_columns__: ClassVar[dict[str, Column[Any]]]

    def __init__(self, **values: object) -> None:
        """Build a row instance; keys may be attribute names or SQL column names."""

        for name, column_obj in self.__mango_columns__.items():
            if name in values:
                setattr(self, name, values[name])
            elif column_obj.column_name in values:
                setattr(self, name, values[column_obj.column_name])


def to_snake_case(name: str) -> str:
    """SQL table name from a class name (``UserProfile`` -> ``user_profile``)."""

    chars: list[str] = []

    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            chars.append("_")

        chars.append(char.lower())

    return "".join(chars)
