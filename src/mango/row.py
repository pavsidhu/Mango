from __future__ import annotations

from typing import Any, ClassVar, cast, overload

from mango.expressions import Expr


class RowColumn[T]:
    expression: Expr[T]
    name: str

    def __init__(self, expression: Expr[T]) -> None:
        self.expression = expression
        self.name = ""

    def bind(self, name: str) -> None:
        self.name = name

    @property
    def python_type(self) -> type[T]:
        return self.expression.python_type

    @overload
    def __get__(self, instance: None, owner: type[Row]) -> RowColumn[T]: ...

    @overload
    def __get__(self, instance: Row, owner: type[Row]) -> T: ...

    def __get__(self, instance: Row | None, owner: type[Row]) -> RowColumn[T] | T:
        if instance is None:
            return self
        storage = cast(dict[str, Any], object.__getattribute__(instance, "__dict__"))
        return storage[self.name]

    def __set__(self, instance: Row, value: T) -> None:
        storage = cast(dict[str, Any], object.__getattribute__(instance, "__dict__"))
        storage[self.name] = value


class RowMeta(type):
    def __new__(
        cls,
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        created: Any = super().__new__(cls, name, bases, namespace, **kwargs)
        if name == "Row" and created.__module__ == __name__:
            return created

        inherited: dict[str, RowColumn[Any]] = {}
        for base in bases:
            inherited.update(getattr(base, "__mango_columns__", {}))

        own_columns: dict[str, RowColumn[Any]] = {
            attr_name: value
            for attr_name, value in namespace.items()
            if isinstance(value, RowColumn)
        }
        columns: dict[str, RowColumn[Any]] = {**inherited, **own_columns}

        for attr_name, row_column in columns.items():
            row_column.bind(attr_name)

        created.__mango_columns__ = columns
        return created


class Row(metaclass=RowMeta):
    __mango_columns__: ClassVar[dict[str, RowColumn[Any]]]

    def __init__(self, **values: object) -> None:
        for name in self.__mango_columns__:
            if name in values:
                setattr(self, name, values[name])


def column[T](expression: Expr[T]) -> RowColumn[T]:
    return RowColumn(expression)


def is_row_type(value: type[Any]) -> bool:
    return issubclass(value, Row)


def row_projection(value: type[Any]) -> dict[str, Expr[Any]]:
    if not is_row_type(value):
        raise TypeError("Expected a Row subclass")
    return {
        name: row_column.expression
        for name, row_column in value.__mango_columns__.items()
    }
