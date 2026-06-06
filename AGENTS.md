# Project Goals

Mango is a type-safe ORM for Python. The project should make static type
inference the core product experience, not a nice-to-have layered on top of a
dynamic ORM.

The ORM targets Python 3.13 and newer. Do not spend design effort preserving
backwards compatibility with older Python versions or legacy APIs.

## Core Principles

- Model definitions must be type-safe. Declaring a model field should preserve
  the Python type of that field for static checkers and downstream query code.
- Queries must be type-safe. Query builders should preserve result row types
  through selection, filtering, ordering, projection, and execution.
- Prefer APIs that static type checkers can understand naturally. Runtime
  validation is useful, but it should not be the primary way users discover type
  mistakes when Python's type system can express the relationship.
- When Python cannot currently express a type relationship statically, keep the
  runtime validation small, explicit, and documented near the API boundary.
- Query syntax should be as SQL-like as possible while still feeling natural in
  Python. Drizzle's TypeScript API is the closest north star: composable,
  explicit, strongly typed query construction that maps clearly to SQL.
- Keep the SQL compiler and database executor separated. Query construction and
  SQL generation should be inspectable without requiring a live database.

## Design Direction

Favor explicit model, expression, projection, and query types over magic
dynamic behavior. A user should be able to read a query and predict both the SQL
shape and the Python result type.

When adding features, ask whether the API keeps these properties:

- Field access carries the declared field type.
- Comparisons and SQL expressions produce typed expression objects.
- Select queries preserve the projected row type.
- Result hydration matches the statically declared projection.
- The generated SQL remains close to the query builder syntax.

If a feature makes the static type story weaker, prefer a smaller feature with a
clearer type model.
