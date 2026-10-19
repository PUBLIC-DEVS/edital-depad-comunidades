import pytest
from django.core.exceptions import ValidationError

from apps.institutions.cnpj import (
    classify_cnpj_relationship,
    cnpj_branch_label,
    cnpj_validator,
    compare_cnpj,
    extract_cnpj_branch,
    extract_cnpj_root,
    format_cnpj,
    format_cnpj_root,
    is_matriz_cnpj,
    normalize_cnpj,
    validate_alphanumeric_cnpj,
    validate_cnpj,
    validate_legacy_numeric_cnpj,
)


class TestCNPJModule:
    # CNPJ de teste com dígitos válidos (ex: Banco do Brasil)
    VALID_NUMERIC_CNPJ = "00.000.000/0001-91"
    VALID_NUMERIC_RAW = "00000000000191"
    VALID_FILIAL_CNPJ = "00.000.000/0002-72"

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

    def test_cnpj_root_and_branch_helpers(self):
        assert extract_cnpj_root(self.VALID_NUMERIC_CNPJ) == "00000000"
        assert format_cnpj_root(self.VALID_NUMERIC_CNPJ) == "00.000.000"
        assert extract_cnpj_branch(self.VALID_NUMERIC_CNPJ) == "0001"
        assert extract_cnpj_branch(self.VALID_FILIAL_CNPJ) == "0002"
        assert is_matriz_cnpj(self.VALID_NUMERIC_CNPJ) is True
        assert is_matriz_cnpj(self.VALID_FILIAL_CNPJ) is False
        assert cnpj_branch_label(self.VALID_NUMERIC_CNPJ) == "Matriz (0001)"
        assert cnpj_branch_label(self.VALID_FILIAL_CNPJ) == "Filial (0002)"

    def test_classify_cnpj_relationship_matriz_filial(self):
        rel_same_root = classify_cnpj_relationship(
            self.VALID_NUMERIC_CNPJ,
            self.VALID_FILIAL_CNPJ,
        )
        assert rel_same_root["relation"] == "SAME_ROOT_MATRIZ_FILIAL"
        assert rel_same_root["same_root"] is True
        assert rel_same_root["exact_match"] is False
        assert rel_same_root["is_matriz_filial_pair"] is True

        rel_exact = classify_cnpj_relationship(
            self.VALID_NUMERIC_CNPJ,
            self.VALID_NUMERIC_RAW,
        )
        assert rel_exact["relation"] == "EXACT_MATCH"
        assert rel_exact["exact_match"] is True

        rel_diff = classify_cnpj_relationship(
            self.VALID_NUMERIC_CNPJ,
            "11.222.333/0001-81",
        )
        assert rel_diff["relation"] == "DIFFERENT_ROOT"
        assert rel_diff["same_root"] is False
