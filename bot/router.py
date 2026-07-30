"""Routing table for bidirectional bridges.

A bridge ``[A, B]`` mirrors messages both ways, so it expands into two
directed routes: A -> B and B -> A. The table maps each source chat id to
the list of destination chat ids it should copy to.
"""

from __future__ import annotations

from collections.abc import Iterable


class RouteTable:
    """Maps a source chat id to its destination chat ids."""

    def __init__(self) -> None:
        self._routes: dict[int, list[int]] = {}

    @classmethod
    def from_bridges(cls, bridges: Iterable[tuple[int, int]]) -> "RouteTable":
        table = cls()
        for a, b in bridges:
            table._add(a, b)
            table._add(b, a)
        return table

    def _add(self, source: int, dest: int) -> None:
        dests = self._routes.setdefault(source, [])
        if dest not in dests:  # de-dup
            dests.append(dest)

    def destinations(self, source: int) -> list[int]:
        """Return destinations for a source chat id (empty if none)."""
        return self._routes.get(source, [])

    @property
    def sources(self) -> list[int]:
        """All configured source chat ids."""
        return list(self._routes.keys())

    def __len__(self) -> int:
        """Number of directed routes."""
        return sum(len(d) for d in self._routes.values())
