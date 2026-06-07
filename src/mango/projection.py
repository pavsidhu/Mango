from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mango.row import is_row_type


def hydrate_row[T](result_type: type[T], row: Mapping[str, Any]) -> T:
    if not is_row_type(result_type):
        raise TypeError("Projection result type must be a Row subclass")
    return result_type(**dict(row))
