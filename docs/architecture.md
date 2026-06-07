# Architecture

Mango is a small type-safe PostgreSQL ORM. Its internal representation is typed
SQL chunks plus immutable query configuration.

The package is currently organized around these layers:

- schema descriptors and table metadata
- composable typed SQL chunks
- typed expressions and SQL helper functions
- `Row`-based result projections and hydration
- immutable `Select[T]` query configuration
- PostgreSQL compilation and async psycopg execution

## Schema Metadata

`Table` uses `TableMeta` to bind `Column[T]` descriptors to table metadata.
Postgres-specific type helpers such as `integer()`, `varchar()`, and `uuid()`
live in `mango.pg.columns` and return typed columns, so Pyright can infer table
column types directly from class bodies without a separate Python type argument.
Import them from `mango.pg` (or `mango.pg.columns`).

Each table class receives `__mango_table__` and `__mango_columns__`. Table names
default to a simple snake_case version of the class name and can be overridden
with `__tablename__`. Each `TableMetadata` owns a `TableRef`, and each bound
column stores an `SQL[T]` fragment containing a structured `ColumnRef`.

Column instances serve two roles:

- on the class, `User.age` is a `Column[int]` and can be used in queries
- on an instance, `user.age` is an `int` stored in the row instance dict

## Typed SQL Chunks

`SQL[T]` is Mango's central composable SQL fragment. It contains ordered chunks:

- raw SQL text for trusted syntax such as operators, parentheses, and function
  names
- column references
- bound parameters
- nested `SQL[T]` fragments
- nested `Select[T]` queries for forms such as `EXISTS (...)`

`SQL[T]` computes `used_tables`, similar to Drizzle's `usedTables`. Mango uses
that metadata to infer `FROM` sources when a query has no explicit `.from_(...)`.
Explicit `FROM` and join configuration lives on `Select[T]`.

Mango uses chunks instead of a full expression tree because expressions are
mostly written in SQL order already. A binary comparison such as `User.age > 18`
becomes a typed sequence of chunks: open parenthesis, the column fragment, a
trusted operator chunk, a parameter chunk, and a close parenthesis. This keeps
the SQL shape easy to inspect without requiring a second render tree.

User values are stored as parameter chunks, and table/column identifiers remain
structured references until the dialect compiler turns those chunks into final
SQL text and placeholder syntax. `raw_expr()` is the explicit escape hatch for
trusted SQL that cannot yet be expressed through Mango's typed helpers.

## Expressions

`Expr[T]` wraps `SQL[T]` and the Python result type for that expression.
`Column[T]` subclasses `Expr[T]`, so comparisons such as `User.age > 18` return
`Expr[bool]`.

The expression layer currently covers:

- comparison, arithmetic, `IS NULL`, `IS DISTINCT FROM`, `BETWEEN`, `IN`, and
  pattern matching helpers
- boolean composition with `and_()`, `or_()`, and `not_()`
- literals, raw expressions, generic SQL functions, `count()`, `case()`, and
  `exists()`
- ordering metadata with direction and `NULLS FIRST` / `NULLS LAST`
- grouping helpers for `ROLLUP`, `CUBE`, `GROUPING SETS`, and the empty grouping
  set

All of these helpers return typed `Expr[T]` objects so projected row attributes
and query conditions preserve their static types.

## Projection Model

Mango projections use `Row` subclasses:

```python
class UserResult(Row):
    name = expr(User.name)
    age = expr(User.age)

query = select(UserResult)
```

`expr(User.name)` returns `RowExpr[str]`, so instance attributes retain the
source expression type without writing `str` or `int` twice. `select(UserResult)`
validates that the target is a `Row` subclass, derives its projection from
`__mango_exprs__`, and returns `Select[UserResult]`.

The selected aliases and expressions come only from the target `Row` subclass.
Dataclass and `TypedDict` result projections are intentionally unsupported to
keep the public projection model small and statically predictable.

Hydration is deliberately small: executor rows are dictionaries keyed by selected
aliases, and `hydrate_row()` constructs the requested `Row` subclass with those
values.

## Query Config

`Select[T]` is an immutable dataclass that stores query config directly. Methods
return a new `Select[T]`, preserving the result type through the chain and
leaving the compiler to consume the config object directly.

The current `Select[T]` model covers the main PostgreSQL `SELECT` surface:

- CTEs with `.with_(...)`, including recursive and materialization options
- `ALL`, `DISTINCT`, and `DISTINCT ON`
- explicit `.from_(...)`, `from_table(...)`, `ONLY`, descendants, and
  `TABLESAMPLE`
- inner, left, right, full, cross, natural, and lateral joins
- `WHERE`, `GROUP BY`, `HAVING`, named windows, and set operations
- `ORDER BY`, `LIMIT`, `OFFSET`, SQL-standard `FETCH`, and row locks

When `.from_(...)` is omitted, the compiler looks at projection, condition,
ordering, grouping, and having expressions to infer table sources from
`SQL.used_tables`. Scalar projections with no table references compile without a
`FROM` clause.

`Select[T]` also exposes async execution helpers:

- `.all()` returns `list[T]`
- `.first()` returns `T | None`
- `.one()` returns `T` and requires exactly one row

These helpers use the currently bound executor and then hydrate rows into the
query's `Row` result type.

## SQL Compiler and Executor

`PostgresCompiler.compile_select()` consumes `Select[T]` and returns
`CompiledSql`. It renders query configuration and `SQL[T]` chunks recursively
and centrally handles:

- identifier quoting
- table, column, table sample, join, grouping, window, fetch, and locking syntax
- placeholder numbering
- bound parameter collection
- nested SQL fragments and nested select queries

`PostgresCompiler()` emits `$1` numeric placeholders for inspection. The psycopg
executor uses `PostgresCompiler(param_style="pyformat")`, which emits `%s`
placeholders because psycopg3 expects that parameter style.

`PostgresExecutor` owns psycopg3 execution. `connect()` creates an async
connection, binds the executor in a `ContextVar`, and resets it when the context
exits. Lower-level callers can also use `bind_executor()` and `reset_executor()`
directly.

The compiler remains independent from psycopg, so query construction and SQL
generation are inspectable without a live database.