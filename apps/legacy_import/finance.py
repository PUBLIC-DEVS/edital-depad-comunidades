"""Recognize the explicit historical U/V formulas; never evaluate arbitrary Excel code."""

import re
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.editais.models import FundingRule


def configure_source_finance(data, edital):
    patterns = set()
    percentages = set()
    for record in data.distribution:
        formula = record["formulas"].get("U", "")
        match = re.search(
            r"N\d+\*(\d+\.\d+)\).*?O\d+\*(\d+\.\d+)\).*?P\d+\*(\d+\.\d+)\).*?\*\s*(\d+)",
            formula,
        )
        if match:
            patterns.add(match.groups())
        equity = record["formulas"].get("V", "")
        match = re.search(r"U\d+\*(0\.\d+)", equity)
        if match:
            percentages.add(Decimal(match[1]) * 100)
    if not patterns and not percentages:
        return False  # A values-only workbook cannot prove its underlying financial rule.
    if len(patterns) != 1 or len(percentages) != 1:
        raise ValidationError("Financial source formulas absent, mixed or unsupported")
    female, male, nursing, months = patterns.pop()
    for kind, value in zip(FundingRule.VacancyType.values, (female, male, nursing), strict=True):
        rule, _ = FundingRule.objects.get_or_create(
            edital=edital,
            vacancy_type=kind,
            defaults={"monthly_value": Decimal(value), "duration_months": int(months)},
        )
        if rule.monthly_value != Decimal(value) or rule.duration_months != int(months):
            raise ValidationError("Configured financial rule conflicts with source formula")
    percentage = percentages.pop()
    if edital.minimum_equity_percentage != percentage:
        raise ValidationError("Configured equity percentage conflicts with source formula")
    return True
