from mango import Row, Table, expr, select
from mango.pg import PostgresCompiler, connect, integer, uuid, varchar


class User(Table):
    id = uuid(primary_key=True)
    name = varchar()
    age = integer()


class UserResult(Row):
    name = expr(User.name)
    age = expr(User.age)


query = select(UserResult).where(User.age > 18).order_by(User.name).limit(25)


compiled = PostgresCompiler().compile_select(query)
print(compiled.sql)
print(compiled.params)


async def run(dsn: str) -> list[UserResult]:
    async with connect(dsn):
        return await query
