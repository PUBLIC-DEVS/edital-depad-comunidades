import pytest

from apps.institutions.cnpj import compare_cnpj, format_cnpj, normalize_cnpj, validate_cnpj


@pytest.mark.parametrize(
    "value,expected",
    [
        ("00.000.000/E08G-12", True),
        ("12.ABC.345/01DE-35", True),
        ("00.000.000/e08g-12", True),
        ("00.000.000/E08G-13", False),
        ("00.000.000/0001-91", True),
        ("00.000.000/0001-92", False),
    ],
)
def test_official_checksums(value, expected):
    # Official RFB manual and first registered alpha CNPJ; no generated DV oracle.
    assert validate_cnpj(value) is expected


def test_alpha_normalization_formatting_and_comparison():
    assert normalize_cnpj(" 00.000.000/e08g-12 ") == "00000000E08G12"
    assert format_cnpj("00000000e08g12") == "00.000.000/E08G-12"
    assert compare_cnpj("00.000.000/e08g-12", "00000000E08G12")
