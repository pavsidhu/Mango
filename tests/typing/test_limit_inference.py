"""Probe: can return type depend on literal limit()?"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, overload

from mango import Row


type LimitState = None | Literal[1] | int


@dataclass(frozen=True)
class SelectWithLimit[T: Row, L: LimitState = None]:
    result_type: type[T]
    limit_value: int | None = None

    @overload
    def limit(self, value: Literal[1], /) -> SelectWithLimit[T, Literal[1]]: ...

    @overload
    def limit(self, value: int, /) -> SelectWithLimit[T, int]: ...

    def limit(self, value: int, /) -> SelectWithLimit[T, LimitState]:
        return replace(self, limit_value=value)

    @overload
    async def fetch(self: SelectWithLimit[T, Literal[1]]) -> T | None: ...

    @overload
    async def fetch(self: SelectWithLimit[T, None]) -> list[T]: ...

    @overload
    async def fetch(self: SelectWithLimit[T, int]) -> list[T]: ...

    async def fetch(self) -> list[T] | T | None:
        raise NotImplementedError


class UserRow(Row):
    name: str


async def demo(page_size: int) -> None:
    q = SelectWithLimit(result_type=UserRow)
    many = await q.fetch()
    one = await q.limit(1).fetch()
    dynamic = await q.limit(page_size).fetch()

    reveal_type(many)  # expect list[UserRow]
    reveal_type(one)  # expect UserRow | None
    reveal_type(dynamic)  # expect list[UserRow]
