# Architecture

This MVP is split into five small layers. The core internal representation is
typed SQL chunks, not a SQL AST and not raw SQL strings.

## Schema Metadata

`Model` uses `ModelMeta` to bind `Field[T]` descriptors to table metadata. The
public `field(int)` helper returns `Field[int]`, so Pyright can infer model
column types directly from class bodies.

Each table has a `TableRef`, and each bound field stores an `SQL[T]` fragment
containing a `ColumnRef`. The reference survives query construction unchanged
until a dialect compiler renders it.

## Typed SQL Chunks

`SQL[T]` is Mango's central composable SQL fragment. It contains ordered chunks:

- trusted raw SQL text for Mango-owned syntax such as operators and parentheses
- column references
- bound parameters
- nested `SQL[T]` fragments

`SQL[T]` also computes `used_tables`, similar to Drizzle's `usedTables`. Mango
uses that small amount of metadata to infer a single `FROM` table for now.

Mango uses chunks instead of a full tree because expressions are mostly written
in SQL order already. A binary comparison such as `User.age > 18` becomes a
typed sequence of chunks: open parenthesis, the column fragment, a trusted
operator chunk, a parameter chunk, and a close parenthesis. This keeps the SQL
shape easy to inspect without requiring a second expression tree.

Mango also avoids raw strings as the expression representation. User values are
stored as parameter chunks, and table/column identifiers remain structured
references until the dialect compiler turns those chunks into final SQL text
and placeholder syntax.

## Expressions

`Expr[T]` wraps `SQL[T]` and the Python result type for that expression.
`Field[T]` subclasses `Expr[T]`, so comparisons such as `User.age > 18` return
`Expr[bool]`. SQL functions follow the same pattern; `count(User.id)` returns
`Expr[int]` by composing nested chunks.

## Query Config

`Select[T]` is an immutable dataclass that stores query config directly:
projections, conditions, ordering, limit, and offset. Methods such as
`.where()`, `.order_by()`, `.limit()`, and `.offset()` return a new `Select[T]`,
preserving the result type through the whole chain.

There is no hidden query render tree. The compiler accepts `Select[T]` directly.

## Projection Validation

Mango projections use `Row` subclasses:

```python
class UserResult(Row):
    name = column(User.name)
    age = column(User.age)

query = select(UserResult)
```

`column(User.name)` returns `RowColumn[str]`, so instance attributes retain the
source field type without writing `str` or `int` twice. `select(UserResult)`
derives its projection from the row class and still returns `Select[UserResult]`.

Runtime validation checks that explicit projection aliases exist on the target
`Row` subclass and that every projected expression carries the expected Python
type. Dataclass and `TypedDict` result projections are intentionally unsupported
to keep the public projection model small and statically predictable.

## SQL Compiler and Executor

`PostgresCompiler.compile_select()` consumes `Select[T]` and returns
`CompiledSql`. It renders `SQL[T]` chunks recursively and centrally handles:

- identifier quoting
- table and column rendering
- placeholder numbering
- bound parameter collection
- nested SQL fragments

`PostgresCompiler()` emits `$1` numeric placeholders for inspection. The
psycopg executor uses `PostgresCompiler(param_style="pyformat")`, which emits
`%s` placeholders because psycopg3 expects that parameter style.

`PostgresExecutor` owns psycopg3 execution and maps rows back into dictionaries
for hydration. The compiler remains independent from psycopg, so query
construction and SQL generation are inspectable without a live database.
