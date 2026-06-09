from typing import reveal_type

from mango import Row, Table, expr, select
from mango.pg import integer, uuid, varchar


class User(Table):
    id = uuid(primary_key=True)
    name = varchar()
    age = integer()


class UserRowResult(Row):
    name = expr(User.name)
    age = expr(User.age)


row_query = select(UserRowResult)
row_result = UserRowResult(name="Ada", age=37)

reveal_type(User.id)
reveal_type(User.name)
reveal_type(User.age > 18)
reveal_type(UserRowResult.name)
reveal_type(row_result.name)
reveal_type(row_query)


async def fetch_users() -> None:
    users = await row_query

    reveal_type(users)
