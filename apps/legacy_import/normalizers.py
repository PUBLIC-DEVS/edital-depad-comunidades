import re
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from openpyxl.utils.datetime import from_excel


def text(value):
    return "" if value is None else str(value).strip()


def normalized_text(value):
    return " ".join(
        "".join(
            c for c in unicodedata.normalize("NFD", text(value)) if unicodedata.category(c) != "Mn"
        )
        .upper()
        .split()
    )


def normalize_status(value, column):
    raw = normalized_text(value)
    statuses = {
        "ATENDE": "ATENDE",
        "NAO ATENDE": "NAO_ATENDE",
        "NAO ENVIADO": "NAO_ENVIADO",
        "ISENTO": "NAO_APLICAVEL",
        "NAO APLICAVEL": "NAO_APLICAVEL",
        "N/A": "NAO_APLICAVEL",
        "": "EM_BRANCO",
    }
    if column == "BV":
        statuses["ENVIADO"] = "ATENDE"
    return statuses.get(raw)


def normalize_review(value):
    raw = normalized_text(value).replace("-", " ").replace("_", " ")
    return {
        "PRE HABILITADO": "PRE_HABILITADO",
        "PRE HABILLITADO": "PRE_HABILITADO",
        "PRE INABILITADO": "PRE_INABILITADO",
    }.get(raw)


def parse_timestamp(day, clock, epoch):
    """Combine F/G explicitly, without substituting import time for missing history."""
    if day is None or clock is None:
        raise ValueError("Missing official date/time")
    if isinstance(day, (float, int)):
        day = from_excel(day, epoch)
    if isinstance(day, str):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S"):
            try:
                day = datetime.strptime(day.strip(), fmt)
                break
            except ValueError:
                continue
    if isinstance(day, datetime):
        day = day.date()
    if isinstance(clock, (float, int)):
        clock = from_excel(clock, epoch)
    if isinstance(clock, datetime):
        clock = clock.time()
    if isinstance(clock, str):
        clock = time.fromisoformat(clock.strip())
    if not isinstance(day, date) or not isinstance(clock, time):
        raise ValueError("Invalid official date/time")
    return timezone.make_aware(datetime.combine(day, clock), timezone.get_default_timezone())


def decimal_value(value):
    if value in (None, ""):
        return None
    raw = text(value).replace("R$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        result = Decimal(raw)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def failed_codes(value):
    return sorted(set(re.findall(r"4\.2\s*[-–]?\s*([IVX]+)", text(value).upper())))


def json_value(value):
    if isinstance(value, (datetime, date, time, Decimal)):
        return str(value)
    # openpyxl array-formula objects are source formula descriptors, not values.
    if hasattr(value, "text"):
        return value.text
    return value
