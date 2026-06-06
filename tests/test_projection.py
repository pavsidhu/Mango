from typing import TypedDict

import pytest

from mango import Model, Row, column, field, select
from mango.projection import hydrate_row


class User(Model):
    id = field(int, primary_key=True)
    name = field(str)
    age = field(int)


class UserDictResult(TypedDict):
    name: str
    age: int


class UserRowResult(Row):
    name = column(User.name)
    age = column(User.age)


class UserPlainResult:
    name: str
    age: int


def test_row_projection_is_inferred_from_class() -> None:
    query = select(UserRowResult)

    assert list(query.projections) == ["name", "age"]
    assert query.projections["name"] is User.name
    assert query.projections["age"] is User.age


def test_select_rejects_typed_dict_result_type() -> None:
    with pytest.raises(TypeError, match="Row subclass"):
        select(UserDictResult, name=User.name, age=User.age)


def test_select_rejects_plain_result_type() -> None:
    with pytest.raises(TypeError, match="Row subclass"):
        select(UserPlainResult, name=User.name, age=User.age)


def test_projection_validation_rejects_wrong_expression_type() -> None:
    with pytest.raises(TypeError, match="age"):
        select(UserRowResult, name=User.name, age=User.name)


def test_projection_validation_rejects_missing_required_field() -> None:
    with pytest.raises(TypeError, match="age"):
        select(UserRowResult, name=User.name)


def test_hydrates_row_class_rows() -> None:
    result = hydrate_row(UserRowResult, {"name": "Ada", "age": 37})

    assert result.name == "Ada"
    assert result.age == 37


def test_hydrate_rejects_non_row_result_type() -> None:
    with pytest.raises(TypeError, match="Row subclass"):
        hydrate_row(UserDictResult, {"name": "Ada", "age": 37})
