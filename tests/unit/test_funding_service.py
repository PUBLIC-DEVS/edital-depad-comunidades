from decimal import Decimal

import pytest
from django.utils import timezone

from apps.editais.models import Edital, FundingRule
from apps.submissions.services import FundingRuleNotFoundError, FundingService


@pytest.mark.django_db
class TestFundingService:
    @pytest.fixture
    def edital(self):
        now = timezone.now()
        ed = Edital.objects.create(
            name="Edital Financeiro",
            number="02",
            year=2024,
            opens_at=now,
            closes_at=now + timezone.timedelta(days=30),
        )
        FundingRule.objects.create(
            edital=ed,
            target_group="G1",
            monthly_value_per_vacancy=Decimal("2500.00"),
            duration_months=12,
            minimum_equity_percentage=Decimal("10.00"),
        )
        FundingRule.objects.create(
            edital=ed,
            target_group="GERAL",
            monthly_value_per_vacancy=Decimal("2000.00"),
            duration_months=12,
            minimum_equity_percentage=Decimal("5.00"),
        )
        return ed

    def test_calculate_monthly_and_global_value(self, edital):
        # 10 vagas no grupo G1: 10 * 2500.00 = 25000.00
        monthly = FundingService.calculate_monthly_value(edital, "G1", 10)
        assert monthly == Decimal("25000.00")

        # Global 12 meses: 25000.00 * 12 = 300000.00
        global_val = FundingService.calculate_global_value(edital, "G1", 10)
        assert global_val == Decimal("300000.00")

        # Global com meses customizados: 6 meses = 150000.00
        global_custom = FundingService.calculate_global_value(edital, "G1", 10, duration_months=6)
        assert global_custom == Decimal("150000.00")

    def test_minimum_equity_and_adequacy(self, edital):
        valor_global = Decimal("300000.00")
        # G1 exige 10%: 30000.00
        min_equity = FundingService.calculate_minimum_equity(edital, "G1", valor_global)
        assert min_equity == Decimal("30000.00")

        # Declarado 35000 -> Suficiente
        assert (
            FundingService.validate_equity_adequacy(edital, "G1", valor_global, Decimal("35000.00"))
            is True
        )

        # Declarado 25000 -> Insuficiente
        assert (
            FundingService.validate_equity_adequacy(edital, "G1", valor_global, Decimal("25000.00"))
            is False
        )

    def test_fallback_to_geral_and_not_found(self, edital):
        # Grupo G3 não tem regra específica, deve usar a GERAL (2000.00/vaga)
        monthly = FundingService.calculate_monthly_value(edital, "G3", 5)
        assert monthly == Decimal("10000.00")

        # Edital sem nenhuma regra deve lançar FundingRuleNotFoundError
        ed_empty = Edital.objects.create(
            name="Sem regras",
            number="99",
            year=2024,
            opens_at=timezone.now(),
            closes_at=timezone.now(),
        )
        with pytest.raises(FundingRuleNotFoundError):
            FundingService.get_funding_rule(ed_empty, "G1")
