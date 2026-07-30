"""Tests for RouteTable — pure logic, no mocks, no network."""

from bot.router import RouteTable


def test_bidirectional_bridge():
    table = RouteTable.from_bridges([(1, 2)])
    assert table.destinations(1) == [2]
    assert table.destinations(2) == [1]


def test_shared_group_across_two_bridges():
    # Group 2 is in both bridges -> forwards to both 1 and 3.
    table = RouteTable.from_bridges([(1, 2), (2, 3)])
    assert table.destinations(2) == [1, 3]
    assert table.destinations(1) == [2]
    assert table.destinations(3) == [2]


def test_duplicate_destination_is_deduped():
    table = RouteTable.from_bridges([(1, 2), (1, 2)])
    assert table.destinations(1) == [2]
    assert table.destinations(2) == [1]


def test_unknown_source_has_no_destinations():
    table = RouteTable.from_bridges([(1, 2)])
    assert table.destinations(999) == []


def test_len_counts_directed_routes():
    table = RouteTable.from_bridges([(1, 2), (3, 4)])
    assert len(table) == 4  # 1->2, 2->1, 3->4, 4->3


def test_sources_lists_all_source_ids():
    table = RouteTable.from_bridges([(1, 2)])
    assert sorted(table.sources) == [1, 2]
