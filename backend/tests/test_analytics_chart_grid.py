"""Row normalisation for the dashboard export.

`/reports/analytics` takes a free-form dict, so the shape of `rows` is whatever
the caller sent. These pin down what is accepted and — just as importantly —
that a shape we cannot use raises ValidationError rather than an AttributeError
the route would surface as a 500.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.services.report_service import _chart_grid


# ---------------------------------------------------------------------------
# Rows keyed by column — what the frontend sends
# ---------------------------------------------------------------------------

def test_dict_rows_infer_their_columns() -> None:
    columns, rows = _chart_grid({
        "title": "By status",
        "rows": [{"status": "New", "count": 12}, {"status": "Resolved", "count": 30}],
    })

    assert columns == ["status", "count"]
    assert rows == [["New", 12], ["Resolved", 30]]


def test_declared_columns_win_over_inference() -> None:
    """Declaring columns is how a caller controls order and drops fields."""
    columns, rows = _chart_grid({
        "columns": ["count", "status"],
        "rows": [{"status": "New", "count": 12, "internal_id": 99}],
    })

    assert columns == ["count", "status"]
    assert rows == [[12, "New"]]


def test_a_missing_key_becomes_blank_not_an_error() -> None:
    columns, rows = _chart_grid({
        "columns": ["status", "count"],
        "rows": [{"status": "New"}],
    })

    assert rows == [["New", ""]]


# ---------------------------------------------------------------------------
# Rows as lists — the obvious shape for a hand-written call
# ---------------------------------------------------------------------------

def test_list_rows_are_accepted_with_declared_columns() -> None:
    columns, rows = _chart_grid({
        "columns": ["Status", "Count"],
        "rows": [["New", 12], ["Resolved", 30]],
    })

    assert columns == ["Status", "Count"]
    assert rows == [["New", 12], ["Resolved", 30]]


def test_list_rows_without_columns_get_generated_headers() -> None:
    columns, rows = _chart_grid({"rows": [["New", 12]]})

    assert columns == ["Column 1", "Column 2"]
    assert rows == [["New", 12]]


def test_a_short_row_is_padded_so_the_table_stays_aligned() -> None:
    _, rows = _chart_grid({"columns": ["A", "B", "C"], "rows": [["only-one"]]})

    assert rows == [["only-one", "", ""]]


def test_a_long_row_is_trimmed_to_the_declared_columns() -> None:
    _, rows = _chart_grid({"columns": ["A", "B"], "rows": [["x", "y", "z", "extra"]]})

    assert rows == [["x", "y"]]


# ---------------------------------------------------------------------------
# Nothing to draw
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chart", [{"rows": []}, {"rows": None}, {}])
def test_an_empty_chart_yields_nothing_rather_than_failing(chart: dict) -> None:
    assert _chart_grid(chart) == ([], [])


# ---------------------------------------------------------------------------
# Shapes we cannot use — a client error, not a server fault
# ---------------------------------------------------------------------------

def test_scalar_rows_are_rejected_with_a_message_naming_the_chart() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _chart_grid({"title": "Broken", "rows": ["just a string"]})

    message = str(excinfo.value)
    assert "Broken" in message
    assert "str" in message


def test_rows_that_are_not_a_list_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _chart_grid({"title": "Wrong", "rows": {"status": "New"}})


def test_a_chart_that_is_not_an_object_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _chart_grid(["not", "a", "chart"])


def test_an_untitled_chart_still_produces_a_readable_message() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _chart_grid({"rows": [42]})

    assert "untitled" in str(excinfo.value)
