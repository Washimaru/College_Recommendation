"""Loading must be authoritative: a school removed from the catalog has to
disappear from the database, or removals silently never take effect."""
from __future__ import annotations

import pytest

from load import MIN_SAFE_ROWS, rows_to_delete


def _catalog(n: int = 358) -> set[str]:
    return {f"school-{i}" for i in range(n)}


def test_identifies_rows_no_longer_in_the_catalog():
    catalog = _catalog()

    assert rows_to_delete(catalog | {"merged-away"}, catalog) == {"merged-away"}


def test_nothing_to_delete_when_they_match():
    catalog = _catalog()

    assert rows_to_delete(catalog, catalog) == set()


def test_refuses_to_prune_from_a_suspiciously_small_catalog():
    """A broken build producing two records must not wipe the table."""
    with pytest.raises(ValueError, match="refusing to prune"):
        rows_to_delete({f"s{i}" for i in range(300)}, {"a", "b"})


def test_allows_pruning_at_the_safety_threshold():
    catalog = {f"s{i}" for i in range(MIN_SAFE_ROWS)}
    existing = catalog | {"gone"}

    assert rows_to_delete(existing, catalog) == {"gone"}
