from mango import (
    Row,
    Table,
    and_,
    case,
    count,
    exists,
    expr,
    from_table,
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


class UserStats(Row):
    name = expr(User.name)
    visit_count = expr(count(User.id))


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
    fallback = select(UserStats).from_(User).group_by(User.name)
    query = (
        select(UserVisitStats)
        .with_("recent_visits", recent_visits, materialized=False)
        .distinct_on(User.name)
        .from_(User)
        .inner_join(Visit, on=Visit.user_id == User.id)
        .where(and_(User.age >= 18, User.age <= 64))
        .group_by(User.name)
        .having(count(Visit.id) > 1)
        .window(
            "visits_by_user",
            partition_by=(User.id,),
            order_by=(Visit.created_at.desc(),),
        )
        .union_all(fallback)
        .order_by(User.name.desc())
        .offset(5, rows=True)
        .fetch(10, with_ties=True)
        .for_update(of=User, skip_locked=True)
    )

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == (
        'WITH "recent_visits" AS NOT MATERIALIZED ('
        'SELECT "visit"."id" AS "id", "visit"."user_id" AS "user_id" '
        'FROM "visit" WHERE ("visit"."created_at" >= $1)'
        ") "
        'SELECT DISTINCT ON ("user"."name") '
        '"user"."name" AS "name", count("visit"."id") AS "visit_count" '
        'FROM "user" '
        'INNER JOIN "visit" ON ("visit"."user_id" = "user"."id") '
        'WHERE (("user"."age" >= $2) AND ("user"."age" <= $3)) '
        'GROUP BY "user"."name" '
        'HAVING (count("visit"."id") > $4) '
        'WINDOW "visits_by_user" AS ('
        'PARTITION BY "user"."id" ORDER BY "visit"."created_at" DESC'
        ") "
        "UNION ALL "
        'SELECT "user"."name" AS "name", count("user"."id") AS "visit_count" '
        'FROM "user" GROUP BY "user"."name" '
        'ORDER BY "user"."name" DESC '
        "OFFSET $5 ROWS "
        "FETCH FIRST $6 ROWS WITH TIES "
        'FOR UPDATE OF "user" SKIP LOCKED'
    )
    assert compiled.params == ("2026-01-01", 18, 64, 1, 5, 10)


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


def test_compiles_tablesample_and_outer_join_forms() -> None:
    sampled_users = from_table(User).tablesample("SYSTEM", literal(12.5), repeatable=7)
    query = (
        select(UserVisitStats)
        .from_(sampled_users)
        .left_join(Visit, on=Visit.user_id == User.id)
        .group_by(User.name)
    )

    compiled = PostgresCompiler().compile_select(query)

    assert compiled.sql == (
        'SELECT "user"."name" AS "name", count("visit"."id") AS "visit_count" '
        'FROM "user" TABLESAMPLE SYSTEM ($1) REPEATABLE ($2) '
        'LEFT JOIN "visit" ON ("visit"."user_id" = "user"."id") '
        'GROUP BY "user"."name"'
    )
    assert compiled.params == (12.5, 7)
