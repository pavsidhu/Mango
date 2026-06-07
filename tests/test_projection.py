from typing import TypedDict

import pytest

from mango import Table, Row, expr, select
from mango.pg import integer, uuid, varchar
from mango.projection import hydrate_row
from mango.row import row_projection


class User(Table):
    id = uuid(primary_key=True)
    name = varchar()
    age = integer()


class UserDictResult(TypedDict):
    name: str
    age: int


class UserRowResult(Row):
    name = expr(User.name)
    age = expr(User.age)


class UserPlainResult:
    name: str
    age: int


def test_row_projection_is_inferred_from_class() -> None:
    query = select(UserRowResult)
    projection = row_projection(query.result_type)

    assert list(projection) == ["name", "age"]
    assert projection["name"] is User.name
    assert projection["age"] is User.age


def test_select_rejects_typed_dict_result_type() -> None:
    with pytest.raises(TypeError, match="Row subclass"):
        select(UserDictResult)


def test_select_rejects_plain_result_type() -> None:
    with pytest.raises(TypeError, match="Row subclass"):
        select(UserPlainResult)


def test_hydrates_row_class_rows() -> None:
    result = hydrate_row(UserRowResult, {"name": "Ada", "age": 37})

    assert result.name == "Ada"
    assert result.age == 37


def test_hydrate_rejects_non_row_result_type() -> None:
    with pytest.raises(TypeError, match="Row subclass"):
        hydrate_row(UserDictResult, {"name": "Ada", "age": 37})
