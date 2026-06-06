from mango import Model, PostgresCompiler, Row, column, connect, field, select


class User(Model):
    id = field(int, primary_key=True)
    name = field(str)
    age = field(int)


class UserResult(Row):
    name = column(User.name)
    age = column(User.age)


query = select(UserResult).where(User.age > 18).order_by(User.name).limit(25)


compiled = PostgresCompiler().compile_select(query)
print(compiled.sql)
print(compiled.params)


async def run(dsn: str) -> list[UserResult]:
    async with connect(dsn):
        return await query.all()
