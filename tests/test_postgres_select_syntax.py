from mango import (
    Row,
    Table,
    and_,
    case,
    count,
    exists,
    expr,
    func,
    literal,
    select,
)
from mango.pg import PostgresCompiler, integer, uuid, varchar


class User(Table):
    id = uuid(primary_key=True)
    name = varchar()
    age = integer()


class Visit(Table):
    id = uuid(primary_key=True)
    user_id = uuid()
    created_at = varchar()


class UserVisitStats(Row):
    name = expr(User.name)
    visit_count = expr(count(Visit.id))


class VisitResult(Row):
    id = expr(Visit.id)
    user_id = expr(Visit.user_id)


class ExpressionResult(Row):
    is_adult = expr(case(bool).when(User.age >= 18, True).else_(False))
    prefix = expr(func("substring", str, User.name, literal(1), literal(3)))
    age_plus_one = expr(User.age + 1)
    has_name = expr(User.name.is_not_null())


class ScalarResult(Row):
    answer = expr(literal(42))


def test_compiles_scalar_select_without_from_clause() -> None:
    query = select(ScalarResult)

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == 'SELECT $1 AS "answer"'
    assert compiled.params == (42,)


def test_compiles_postgres_select_clause_matrix() -> None:
    recent_visits = select(VisitResult).where(Visit.created_at >= "2026-01-01")
    query = (
        select(UserVisitStats)
        .with_("recent_visits", recent_visits)
        .distinct()
        .from_(User)
        .inner_join(Visit, on=Visit.user_id == User.id)
        .where(and_(User.age >= 18, User.age <= 64))
        .group_by(User.name)
        .having(count(Visit.id) > 1)
        .order_by(User.name.desc())
        .offset(5, rows=True)
    )

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == (
        'WITH "recent_visits" AS ('
        'SELECT "visit"."id" AS "id", "visit"."user_id" AS "user_id" '
        'FROM "visit" WHERE ("visit"."created_at" >= $1)'
        ") "
        'SELECT DISTINCT '
        '"user"."name" AS "name", count("visit"."id") AS "visit_count" '
        'FROM "user" '
        'INNER JOIN "visit" ON ("visit"."user_id" = "user"."id") '
        'WHERE (("user"."age" >= $2) AND ("user"."age" <= $3)) '
        'GROUP BY "user"."name" '
        'HAVING (count("visit"."id") > $4) '
        'ORDER BY "user"."name" DESC '
        "OFFSET $5 ROWS"
    )
    assert compiled.params == ("2026-01-01", 18, 64, 1, 5)


def test_compiles_postgres_expression_forms() -> None:
    query = select(ExpressionResult).where(
        and_(
            User.name.ilike("%ada%"),
            User.age.in_([18, 21, 37]),
            User.name != "bot",
            exists(select(VisitResult).from_(Visit).where(Visit.user_id == User.id)),
        )
    )

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == (
        'SELECT CASE WHEN ("user"."age" >= $1) THEN $2 ELSE $3 END AS "is_adult", '
        'substring("user"."name", $4, $5) AS "prefix", '
        '("user"."age" + $6) AS "age_plus_one", '
        '("user"."name" IS NOT NULL) AS "has_name" '
        'FROM "user" '
        "WHERE (((("
        '"user"."name" ILIKE $7) AND ("user"."age" IN ($8, $9, $10))) '
        'AND ("user"."name" <> $11)) '
        'AND EXISTS (SELECT "visit"."id" AS "id", "visit"."user_id" AS "user_id" '
        'FROM "visit" WHERE ("visit"."user_id" = "user"."id")))'
    )
    assert compiled.params == (18, True, False, 1, 3, 1, "%ada%", 18, 21, 37, "bot")


def test_compiles_outer_join_forms() -> None:
    query = (
        select(UserVisitStats)
        .from_(User)
        .left_join(Visit, on=Visit.user_id == User.id)
        .group_by(User.name)
    )

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == (
        'SELECT "user"."name" AS "name", count("visit"."id") AS "visit_count" '
        'FROM "user" '
        'LEFT JOIN "visit" ON ("visit"."user_id" = "user"."id") '
        'GROUP BY "user"."name"'
    )
    assert compiled.params == ()
