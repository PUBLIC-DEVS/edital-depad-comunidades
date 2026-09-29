"""CEP normalization for operational forms; accepts digits or the displayed format."""

import re

from django.core.exceptions import ValidationError


def normalize_postal_code(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"[0-9]{5}-?[0-9]{3}", value):
        raise ValidationError("Informe um CEP com oito dígitos, com ou sem hífen.")
    digits = value.replace("-", "")
    return f"{digits[:5]}-{digits[5:]}"
