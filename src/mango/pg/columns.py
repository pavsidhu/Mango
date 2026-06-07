from __future__ import annotations

from uuid import UUID as PythonUUID

from mango.schema import Column


def uuid(
    *,
    column_name: str | None = None,
    primary_key: bool = False,
) -> Column[PythonUUID]:
    return Column(
        PythonUUID,
        sql_type="uuid",
        column_name=column_name,
        primary_key=primary_key,
    )


def varchar(
    *,
    column_name: str | None = None,
    primary_key: bool = False,
) -> Column[str]:
    return Column(
        str,
        sql_type="varchar",
        column_name=column_name,
        primary_key=primary_key,
    )


def integer(
    *,
    column_name: str | None = None,
    primary_key: bool = False,
) -> Column[int]:
    return Column(
        int,
        sql_type="integer",
        column_name=column_name,
        primary_key=primary_key,
    )
