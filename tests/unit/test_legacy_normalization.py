from datetime import date, time

import pytest
from openpyxl.utils.datetime import WINDOWS_EPOCH

from apps.legacy_import.normalizers import normalize_review, normalize_status, parse_timestamp


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("PRÉ HABILLITADO", "PRE_HABILITADO"),
        ("PRÉ-INABILITADO", "PRE_INABILITADO"),
        ("Sem docts", None),
    ],
)
def test_review_normalization(raw, expected):
    assert normalize_review(raw) == expected


def test_contextual_exemption_and_sent():
    assert normalize_status("ISENTO", "BV") == "NAO_APLICAVEL"
    assert normalize_status("ENVIADO", "BV") == "ATENDE"
    assert normalize_status("ENVIADO", "E") is None


def test_official_timestamp_combines_separate_fields():
    result = parse_timestamp(date(2025, 9, 19), time(11, 12), WINDOWS_EPOCH)
    assert result.isoformat() == "2025-09-19T11:12:00-03:00"
    with pytest.raises(ValueError):
        parse_timestamp("bad", None, WINDOWS_EPOCH)
