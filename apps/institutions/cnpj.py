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


def extract_cnpj_root(value: Any) -> str:
    """Extrai a raiz de 8 caracteres do CNPJ (identificador base da entidade)."""
    norm = normalize_cnpj(value)
    if len(norm) != 14:
        return ""
    return norm[:8]


def extract_cnpj_branch(value: Any) -> str:
    """Extrai o código de ordem de 4 caracteres do CNPJ (0001 = Matriz, 0002+ = Filial)."""
    norm = normalize_cnpj(value)
    if len(norm) != 14:
        return ""
    return norm[8:12]


def format_cnpj_root(value: Any) -> str:
    """Formata a raiz de 8 caracteres do CNPJ no padrão XX.XXX.XXX."""
    root = extract_cnpj_root(value)
    if len(root) != 8:
        return root
    return f"{root[:2]}.{root[2:5]}.{root[5:8]}"


def is_matriz_cnpj(value: Any) -> bool:
    """Retorna True se o CNPJ informado corresponder à Matriz (ordem 0001)."""
    return extract_cnpj_branch(value) == "0001"


def cnpj_branch_label(value: Any) -> str:
    """Retorna rótulo legível identificando Matriz (0001) ou Filial (XXXX)."""
    branch = extract_cnpj_branch(value)
    if not branch:
        return ""
    if branch == "0001":
        return "Matriz (0001)"
    return f"Filial ({branch})"


def classify_cnpj_relationship(canonical_cnpj: Any, document_cnpj: Any) -> dict[str, Any]:
    """Classifica a relação entre o CNPJ da inscrição (Anexo I) e o CNPJ de um documento."""
    canon = normalize_cnpj(canonical_cnpj)
    doc = normalize_cnpj(document_cnpj)
    canon_label = cnpj_branch_label(canon)
    doc_label = cnpj_branch_label(doc)
    root_fmt = format_cnpj_root(canon)

    if len(canon) != 14 or len(doc) != 14:
        return {
            "status": "INCOMPLETE",
            "relation": "MISSING_DOCUMENT",
            "same_root": False,
            "is_exact": False,
            "exact_match": False,
            "is_matriz_filial": False,
            "is_matriz_filial_pair": False,
            "canonical_formatted": format_cnpj(canon),
            "document_formatted": format_cnpj(doc),
            "canonical_label": canon_label,
            "document_label": doc_label,
            "canonical_branch_label": canon_label,
            "document_branch_label": doc_label,
            "root_formatted": root_fmt,
            "badge_label": "",
            "summary": "",
        }

    if canon == doc:
        return {
            "status": "EXACT",
            "relation": "EXACT_MATCH",
            "same_root": True,
            "is_exact": True,
            "exact_match": True,
            "is_matriz_filial": False,
            "is_matriz_filial_pair": False,
            "canonical_formatted": format_cnpj(canon),
            "document_formatted": format_cnpj(doc),
            "canonical_label": canon_label,
            "document_label": doc_label,
            "canonical_branch_label": canon_label,
            "document_branch_label": doc_label,
            "root_formatted": root_fmt,
            "badge_label": f"Mesmo CNPJ · {canon_label}",
            "summary": f"CNPJ do documento coincide exatamente com o da inscrição ({canon_label}).",
        }

    if canon[:8] == doc[:8]:
        has_matriz = "0001" in (canon[8:12], doc[8:12])
        status = "MATRIZ_FILIAL" if has_matriz else "FILIAL_FILIAL"
        badge = (
            f"Vínculo Matriz ↔ Filial (Raiz {root_fmt})"
            if has_matriz
            else f"Mesma Raiz CNPJ · Filiais Distintas ({root_fmt})"
        )
        return {
            "status": status,
            "relation": "SAME_ROOT_MATRIZ_FILIAL",
            "same_root": True,
            "is_exact": False,
            "exact_match": False,
            "is_matriz_filial": True,
            "is_matriz_filial_pair": has_matriz,
            "canonical_formatted": format_cnpj(canon),
            "document_formatted": format_cnpj(doc),
            "canonical_label": canon_label,
            "document_label": doc_label,
            "canonical_branch_label": canon_label,
            "document_branch_label": doc_label,
            "root_formatted": root_fmt,
            "badge_label": badge,
            "summary": (
                f"Mesma raiz CNPJ ({root_fmt}): inscrição é {canon_label} "
                f"e documento pertence à {doc_label}."
            ),
        }

    return {
        "status": "DIFFERENT_ROOT",
        "relation": "DIFFERENT_ROOT",
        "same_root": False,
        "is_exact": False,
        "exact_match": False,
        "is_matriz_filial": False,
        "is_matriz_filial_pair": False,
        "canonical_formatted": format_cnpj(canon),
        "document_formatted": format_cnpj(doc),
        "canonical_label": canon_label,
        "document_label": doc_label,
        "canonical_branch_label": canon_label,
        "document_branch_label": doc_label,
        "root_formatted": root_fmt,
        "badge_label": "Raiz de CNPJ distinta (outra entidade)",
        "summary": (
            f"Raiz de CNPJ divergente: inscrição ({format_cnpj_root(canon)} · {canon_label}) "
            f"difere do documento ({format_cnpj_root(doc)} · {doc_label})."
        ),
    }


def cnpj_validator(value: Any) -> None:
    """Validador para uso em campos de modelos e formulários do Django."""
    norm = normalize_cnpj(value)
    if not norm:
        raise ValidationError("O CNPJ não pode ser vazio.")
    if not validate_cnpj(norm):
        raise ValidationError(f"O CNPJ '{value}' não é válido.")
