"""Módulo dedicado para tratamento, validação e normalização de CNPJ.

Suporta:
1. CNPJ Legado Numérico (14 dígitos com cálculo de módulo 11).
2. Padrão Alfanumérico da Receita Federal (12 caracteres alfanuméricos + 2 dígitos verificadores).
"""

import re
from typing import Any

from django.core.exceptions import ValidationError


def normalize_cnpj(value: Any) -> str:
    """Normaliza o CNPJ removendo pontuações, espaços e convertendo para maiúsculas."""
    if value is None:
        return ""
    raw = str(value).strip().upper()
    # Remove pontos, traços, barras e espaços
    return re.sub(r"[.\-/\s]", "", raw)


def _calc_numeric_dv(digits: list[int], weights: list[int]) -> int:
    """Calcula dígito verificador padrão módulo 11."""
    total = sum(d * w for d, w in zip(digits, weights, strict=False))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def validate_legacy_numeric_cnpj(cnpj: str) -> bool:
    """Valida CNPJ tradicional composto exclusivamente por 14 dígitos numéricos."""
    if len(cnpj) != 14 or not cnpj.isdigit():
        return False

    # Rejeita sequências repetidas (ex: 00000000000000, 11111111111111)
    if len(set(cnpj)) == 1:
        return False

    digits = [int(char) for char in cnpj]

    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv1 = _calc_numeric_dv(digits[:12], weights1)
    if digits[12] != dv1:
        return False

    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv2 = _calc_numeric_dv(digits[:13], weights2)
    return digits[13] == dv2


def _char_to_val_alphanumeric(char: str) -> int:
    """Converte caractere alfanumérico para valor de cálculo conforme regra da Receita Federal.

    Dígitos '0'-'9' -> 0 a 9
    Letras 'A'-'Z' -> valor ASCII - 48 (conforme norma RFB)
    """
    code = ord(char)
    return code - 48


def validate_alphanumeric_cnpj(cnpj: str) -> bool:
    """Valida novo padrão de CNPJ alfanumérico estabelecido pela Receita Federal."""
    if len(cnpj) != 14:
        return False

    # Primeiros 12 caracteres devem ser letras maiúsculas ou dígitos
    root_branch = cnpj[:12]
    if not re.match(r"^[0-9A-Z]{12}$", root_branch):
        return False

    # Últimos 2 caracteres devem ser numéricos (dígitos verificadores)
    dv = cnpj[12:]
    if not dv.isdigit():
        return False

    vals = [_char_to_val_alphanumeric(c) for c in cnpj]

    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total1 = sum(v * w for v, w in zip(vals[:12], weights1, strict=False))
    rem1 = total1 % 11
    dv1 = 0 if rem1 < 2 else 11 - rem1
    if int(dv[0]) != dv1:
        return False

    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    vals_with_dv1 = vals[:12] + [dv1]
    total2 = sum(v * w for v, w in zip(vals_with_dv1, weights2, strict=False))
    rem2 = total2 % 11
    dv2 = 0 if rem2 < 2 else 11 - rem2
    return int(dv[1]) == dv2


def validate_cnpj(value: Any) -> bool:
    """Valida CNPJ aceitando tanto o padrão numérico clássico quanto o alfanumérico."""
    norm = normalize_cnpj(value)
    if len(norm) != 14:
        return False

    if norm.isdigit():
        return validate_legacy_numeric_cnpj(norm)

    return validate_alphanumeric_cnpj(norm)


def format_cnpj(value: Any) -> str:
    """Formata CNPJ no padrão visual clássico XX.XXX.XXX/XXXX-XX."""
    norm = normalize_cnpj(value)
    if len(norm) != 14:
        return norm or ""
    return f"{norm[:2]}.{norm[2:5]}.{norm[5:8]}/{norm[8:12]}-{norm[12:]}"


def compare_cnpj(cnpj1: Any, cnpj2: Any) -> bool:
    """Compara dois CNPJs de forma segura independentemente de formatação."""
    return normalize_cnpj(cnpj1) == normalize_cnpj(cnpj2)


def cnpj_validator(value: Any) -> None:
    """Validador para uso em campos de modelos e formulários do Django."""
    norm = normalize_cnpj(value)
    if not norm:
        raise ValidationError("O CNPJ não pode ser vazio.")
    if not validate_cnpj(norm):
        raise ValidationError(f"O CNPJ '{value}' não é válido.")
