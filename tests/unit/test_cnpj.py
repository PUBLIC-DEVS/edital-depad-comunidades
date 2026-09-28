import pytest
from django.core.exceptions import ValidationError

from apps.institutions.cnpj import (
    cnpj_validator,
    compare_cnpj,
    format_cnpj,
    normalize_cnpj,
    validate_alphanumeric_cnpj,
    validate_cnpj,
    validate_legacy_numeric_cnpj,
)


class TestCNPJModule:
    # CNPJ de teste com dígitos válidos (ex: Banco do Brasil)
    VALID_NUMERIC_CNPJ = "00.000.000/0001-91"
    VALID_NUMERIC_RAW = "00000000000191"

    # CNPJ com dígitos repetidos
    INVALID_REPEATED = "11.111.111/1111-11"

    # CNPJ com dígito verificador errado
    INVALID_CHECKSUM = "00.000.000/0001-99"

    def test_normalize_cnpj(self):
        assert normalize_cnpj(self.VALID_NUMERIC_CNPJ) == self.VALID_NUMERIC_RAW
        assert normalize_cnpj(" 12.345.678/0001-95 \n") == "12345678000195"
        assert normalize_cnpj(None) == ""

    def test_validate_legacy_numeric_cnpj(self):
        assert validate_legacy_numeric_cnpj(self.VALID_NUMERIC_RAW) is True
        assert validate_legacy_numeric_cnpj("00000000000000") is False
        assert validate_legacy_numeric_cnpj("11111111111111") is False
        assert validate_legacy_numeric_cnpj("00000000000199") is False
        assert validate_legacy_numeric_cnpj("123") is False

    def test_validate_alphanumeric_cnpj(self):
        # Exemplo no formato RFB: 12 chars alfanuméricos + 2 DVs numéricos
        # Calculando um par válido manualmente para teste:
        # Se raiz for "12ABC3450001"
        # Teste de validação geral com formato inválido
        assert validate_alphanumeric_cnpj("INVALID_FORMAT") is False
        assert validate_alphanumeric_cnpj("12ABC3450001XX") is False  # DVs não numéricos

    def test_validate_cnpj_general(self):
        assert validate_cnpj(self.VALID_NUMERIC_CNPJ) is True
        assert validate_cnpj(self.VALID_NUMERIC_RAW) is True
        assert validate_cnpj(self.INVALID_CHECKSUM) is False
        assert validate_cnpj(self.INVALID_REPEATED) is False
        assert validate_cnpj("") is False
        assert validate_cnpj(None) is False

    def test_format_cnpj(self):
        assert format_cnpj("00000000000191") == "00.000.000/0001-91"
        assert format_cnpj("123") == "123"

    def test_compare_cnpj(self):
        assert compare_cnpj("00.000.000/0001-91", "00000000000191") is True
        assert compare_cnpj("00000000000191", "00.000.000/0001-92") is False

    def test_cnpj_validator_raises_validation_error(self):
        with pytest.raises(ValidationError):
            cnpj_validator(self.INVALID_CHECKSUM)

        with pytest.raises(ValidationError):
            cnpj_validator("")

        # Não deve levantar exceção para CNPJ válido
        cnpj_validator(self.VALID_NUMERIC_CNPJ)
