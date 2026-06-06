from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mango.expressions import Expr
from mango.row import is_row_type


@dataclass(frozen=True, slots=True)
class ProjectionField:
    python_type: Any
    required: bool


def validate_projection(
    result_type: type[Any],
    projection: Mapping[str, Expr[Any]],
) -> None:
    expected = projection_fields(result_type)
    expected_names = set(expected)
    projection_names = set(projection)

    extra = projection_names - expected_names
    if extra:
        names = ", ".join(sorted(extra))
        raise TypeError(f"Projection contains unknown field(s): {names}")

    missing = {
        name
        for name, spec in expected.items()
        if spec.required and name not in projection_names
    }
    if missing:
        names = ", ".join(sorted(missing))
        raise TypeError(f"Projection is missing required field(s): {names}")

    for name, expr in projection.items():
        expected_type = expected[name].python_type
        if expected_type is Any:
            continue
        if expr.python_type is not expected_type:
            raise TypeError(
                f"Projection field {name!r} expects {expected_type.__name__}, "
                f"got {expr.python_type.__name__}"
            )


def hydrate_row[T](result_type: type[T], row: Mapping[str, Any]) -> T:
    if not is_row_type(result_type):
        raise TypeError("Projection result type must be a Row subclass")
    return result_type(**dict(row))


def projection_fields(result_type: type[Any]) -> dict[str, ProjectionField]:
    if is_row_type(result_type):
        return {
            name: ProjectionField(
                python_type=row_column.python_type,
                required=True,
            )
            for name, row_column in result_type.__mango_columns__.items()
        }

    raise TypeError("Projection result type must be a Row subclass")
