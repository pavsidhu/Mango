from __future__ import annotations

from typing import Any, ClassVar, cast, overload

from mango.expressions import Expr


class RowExpr[T]:
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
    def __get__(self, instance: None, owner: type[Row]) -> RowExpr[T]: ...

    @overload
    def __get__(self, instance: Row, owner: type[Row]) -> T: ...

    def __get__(self, instance: Row | None, owner: type[Row]) -> RowExpr[T] | T:
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

        inherited: dict[str, RowExpr[Any]] = {}
        for base in bases:
            inherited.update(getattr(base, "__mango_exprs__", {}))

        own_exprs: dict[str, RowExpr[Any]] = {
            attr_name: value
            for attr_name, value in namespace.items()
            if isinstance(value, RowExpr)
        }
        exprs: dict[str, RowExpr[Any]] = {**inherited, **own_exprs}

        for attr_name, row_expr in exprs.items():
            row_expr.bind(attr_name)

        created.__mango_exprs__ = exprs
        return created


class Row(metaclass=RowMeta):
    __mango_exprs__: ClassVar[dict[str, RowExpr[Any]]]

    def __init__(self, **values: object) -> None:
        for name in self.__mango_exprs__:
            if name in values:
                setattr(self, name, values[name])


def expr[T](expression: Expr[T]) -> RowExpr[T]:
    return RowExpr(expression)


def is_row_type(value: type[Any]) -> bool:
    return issubclass(value, Row)


def row_projection(value: type[Any]) -> dict[str, Expr[Any]]:
    if not is_row_type(value):
        raise TypeError("Expected a Row subclass")
    return {
        name: row_expr.expression for name, row_expr in value.__mango_exprs__.items()
    }
