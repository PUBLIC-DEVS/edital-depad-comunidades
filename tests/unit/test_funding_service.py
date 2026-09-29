from decimal import Decimal

import pytest

from apps.editais.models import FundingRule
from apps.submissions.services import FundingRuleNotFoundError, FundingService

pytestmark = pytest.mark.django_db


@pytest.fixture
def finance(domain):
    for kind, value in [("FEMALE", "1172.23"), ("MALE", "1172.23"), ("NURSING_MOTHER", "1527.37")]:
        FundingRule.objects.create(
            edital=domain["edital"],
            vacancy_type=kind,
            monthly_value=Decimal(value),
            duration_months=12,
        )
    return domain


@pytest.mark.parametrize(
    "counts,expected",
    [
        ((1, 0, 0), "14066.76"),
        ((0, 1, 0), "14066.76"),
        ((0, 0, 1), "18328.44"),
        ((1, 0, 1), "32395.20"),
        ((1, 1, 1), "46461.96"),
    ],
)
def test_vacancy_types_and_mixtures(finance, counts, expected):
    s = finance["sub"]
    s.vagas_femininas, s.vagas_masculinas, s.vagas_maes_nutrizes = counts
    total, minimum = FundingService.calculate_submission_values(s)
    assert total == Decimal(expected)
    assert minimum == (Decimal(expected) / 10).quantize(Decimal("0.01"))


def test_half_up_cent_rounding(finance):
    assert FundingService.calculate_minimum_equity(finance["edital"], Decimal("0.05")) == Decimal(
        "0.01"
    )


def test_explicit_duration_and_equity(finance):
    ed = finance["edital"]
    assert FundingService.calculate_global_value(ed, "FEMALE", 10, 6) == Decimal("70333.80")
    assert FundingService.validate_equity_adequacy(ed, Decimal("14066.76"), Decimal("1406.68"))
    assert not FundingService.validate_equity_adequacy(ed, Decimal("14066.76"), Decimal("1406.67"))


def test_absent_type_never_falls_back_to_group(domain):
    with pytest.raises(FundingRuleNotFoundError):
        FundingService.get_funding_rule(domain["edital"], "FEMALE")
