from mango import Table, Row, expr, select
from mango.pg import integer, uuid, varchar
from mango.row import hydrate_row, row_projection


class User(Table):
    id = uuid(primary_key=True)
    name = varchar()
    age = integer()


class UserRowResult(Row):
    name = expr(User.name)
    age = expr(User.age)


def test_row_projection_is_inferred_from_class() -> None:
    query = select(UserRowResult)
    projection = row_projection(query.result_type)

    assert list(projection) == ["name", "age"]
    assert projection["name"] is User.name
    assert projection["age"] is User.age


def test_hydrates_row_class_rows() -> None:
    result = hydrate_row(UserRowResult, {"name": "Ada", "age": 37})

    assert result.name == "Ada"
    assert result.age == 37

