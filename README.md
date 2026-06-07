# Mango

A tiny PostgreSQL ORM MVP that treats static type inference as the product.

```python
from mango import Table, Row, expr, select
from mango.pg import integer, uuid, varchar


class User(Table):
    id = uuid(primary_key=True)
    name = varchar()
    age = integer()


class UserResult(Row):
    name = expr(User.name)
    age = expr(User.age)


query = (
    select(UserResult)
    .where(User.age > 18)
    .order_by(User.name)
)
```

Pyright infers `query` as `Select[UserResult]`, `User.id` as
`Column[UUID]`, `User.name` as `Column[str]`, `User.age > 18` as
`Expr[bool]`, and `UserResult().name` as `str`.

```python
from mango.pg import PostgresCompiler

compiled = PostgresCompiler().compile_select(query)
```

Internally, Mango expressions are typed `SQL[T]` fragments made from trusted SQL
text chunks, column references, parameters, and nested fragments. Final SQL
strings and placeholders are assembled only by the dialect compiler.

## Install and Check

```bash
uv sync
uv run pytest
uv run pyright
uv run ty check --python-version 3.13
uv run ruff check
uv run ruff format --check
```

## Runtime Execution

```python
from mango.pg import connect

async with connect("postgresql://localhost/app"):
    users = await query.all()
```

The compiler is independent from psycopg. `PostgresCompiler()` emits `$1`
numeric placeholders for inspection; the psycopg executor uses `%s`
placeholders because psycopg3 expects that parameter style.
