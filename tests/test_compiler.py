from mango import Model, PostgresCompiler, Row, and_, column, count, field, select


class User(Model):
    id = field(int, primary_key=True)
    name = field(str)
    age = field(int)


class UserResult(Row):
    name = column(User.name)
    age = column(User.age)


def test_compiles_basic_select() -> None:
    query = select(UserResult).where(User.age > 18).order_by(User.name)

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == (
        'SELECT "user"."name" AS "name", "user"."age" AS "age" '
        'FROM "user" '
        'WHERE ("user"."age" > $1) '
        'ORDER BY "user"."name" ASC'
    )
    assert compiled.params == (18,)


def test_limit_and_offset() -> None:
    query = select(UserResult).limit(10).offset(20)

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql.endswith("LIMIT $1 OFFSET $2")
    assert compiled.params == (10, 20)


def test_compiles_nested_sql_chunks() -> None:
    query = select(UserResult, name=User.name, age=count(User.id)).where(
        and_(User.age > 18, User.name != "Ada")
    )

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == (
        'SELECT "user"."name" AS "name", count("user"."id") AS "age" '
        'FROM "user" '
        'WHERE (("user"."age" > $1) AND ("user"."name" <> $2))'
    )
    assert compiled.params == (18, "Ada")
