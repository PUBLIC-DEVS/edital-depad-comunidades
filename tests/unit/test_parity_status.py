import pytest

from apps.legacy_import.parity import parity_status


@pytest.mark.parametrize(
    "executed,mismatches,incomplete,expected",
    [
        (False, 0, (), "NOT_RUN"),
        (False, 10, (), "NOT_RUN"),
        (True, 0, ("reviews not compared",), "PARTIAL"),
        (True, 1, (), "FAIL"),
        (True, 0, (), "PASS"),
    ],
)
def test_real_parity_status_requires_external_execution(executed, mismatches, incomplete, expected):
    assert parity_status(executed, mismatches, incomplete) == expected
