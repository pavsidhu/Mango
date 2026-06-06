from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, ClassVar, cast, overload

from mango.expressions import Expr
from mango.sql import TableRef, column_sql


@dataclass(frozen=True, slots=True)
class TableMetadata:
    name: str
    fields: dict[str, Field[Any]]
    sql_ref: TableRef = dataclass_field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sql_ref", TableRef(self.name))


class Field[T](Expr[T]):
    python_type: type[T]
    sql_type: str
    column_name: str
    table: TableMetadata | None
    primary_key: bool

    def __init__(
        self,
        python_type: type[T],
        *,
        sql_type: str | None = None,
        column_name: str | None = None,
        primary_key: bool = False,
    ) -> None:
        self.python_type = python_type
        self.sql_type = sql_type or infer_sql_type(python_type)
        self.column_name = column_name or ""
        self.table = None
        self.primary_key = primary_key
        super().__init__(
            column_sql(TableRef(""), self.column_name),
            python_type,
        )

    def bind(self, table: TableMetadata, attr_name: str) -> None:
        column_name = self.column_name or attr_name
        object.__setattr__(self, "column_name", column_name)
        object.__setattr__(self, "table", table)
        object.__setattr__(
            self,
            "sql",
            column_sql(table.sql_ref, column_name),
        )

    @overload
    def __get__(self, instance: None, owner: type[Model]) -> Field[T]: ...

    @overload
    def __get__(self, instance: Model, owner: type[Model]) -> T: ...

    def __get__(self, instance: Model | None, owner: type[Model]) -> Field[T] | T:
        if instance is None:
            return self
        storage = cast(dict[str, Any], object.__getattribute__(instance, "__dict__"))
        return storage[self.column_name]

    def __set__(self, instance: Model, value: T) -> None:
        storage = cast(dict[str, Any], object.__getattribute__(instance, "__dict__"))
        storage[self.column_name] = value


class ModelMeta(type):
    def __new__(
        cls,
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        created: Any = super().__new__(cls, name, bases, namespace, **kwargs)
        if name == "Model" and created.__module__ == __name__:
            return created

        inherited: dict[str, Field[Any]] = {}
        for base in bases:
            inherited.update(getattr(base, "__mango_fields__", {}))

        own_fields: dict[str, Field[Any]] = {
            attr_name: value
            for attr_name, value in namespace.items()
            if isinstance(value, Field)
        }
        fields: dict[str, Field[Any]] = {**inherited, **own_fields}
        table_name = namespace.get("__tablename__", to_snake_case(name))
        metadata = TableMetadata(table_name, fields)

        for attr_name, field_obj in fields.items():
            field_obj.bind(metadata, attr_name)

        created.__mango_table__ = metadata
        created.__mango_fields__ = fields
        return created


class Model(metaclass=ModelMeta):
    __tablename__: ClassVar[str]
    __mango_table__: ClassVar[TableMetadata]
    __mango_fields__: ClassVar[dict[str, Field[Any]]]

    def __init__(self, **values: object) -> None:
        for name, field_obj in self.__mango_fields__.items():
            if name in values:
                setattr(self, name, values[name])
            elif field_obj.column_name in values:
                setattr(self, name, values[field_obj.column_name])


def field[T](
    python_type: type[T],
    *,
    sql_type: str | None = None,
    column_name: str | None = None,
    primary_key: bool = False,
) -> Field[T]:
    return Field(
        python_type,
        sql_type=sql_type,
        column_name=column_name,
        primary_key=primary_key,
    )


def infer_sql_type(python_type: type[Any]) -> str:
    mapping: dict[type[Any], str] = {
        int: "integer",
        str: "text",
        bool: "boolean",
        float: "double precision",
        bytes: "bytea",
    }
    try:
        return mapping[python_type]
    except KeyError as exc:
        raise TypeError(
            f"No default SQL type is registered for {python_type!r}"
        ) from exc


def to_snake_case(name: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)
