"""Serviço de cálculo e validação das regras financeiras do edital."""

from decimal import Decimal

from apps.editais.models import Edital, FundingRule


class FundingRuleNotFoundError(Exception):
    """Lançada quando não há regra financeira configurada para o grupo/edital."""


class FundingService:
    """Calcula valores mensais, valores globais e patrimônio líquido mínimo exigido."""

    @staticmethod
    def get_funding_rule(edital: Edital, target_group: str) -> FundingRule:
        """Obtém a regra financeira específica do grupo ou a regra geral do edital."""
        rule = FundingRule.objects.filter(edital=edital, target_group=target_group).first()
        if not rule:
            # Fallback para regra geral do edital se cadastrada
            rule = FundingRule.objects.filter(edital=edital, target_group="GERAL").first()

        if not rule:
            msg = f"Nenhuma regra financeira encontrada para o edital {edital} e grupo {target_group}."
            raise FundingRuleNotFoundError(msg)
        return rule

    @classmethod
    def calculate_monthly_value(cls, edital: Edital, target_group: str, vacancies: int) -> Decimal:
        """Calcula o valor financeiro mensal: (valor por vaga) * (número de vagas)."""
        rule = cls.get_funding_rule(edital, target_group)
        return rule.monthly_value_per_vacancy * Decimal(vacancies)

    @classmethod
    def calculate_global_value(
        cls,
        edital: Edital,
        target_group: str,
        vacancies: int,
        duration_months: int | None = None,
    ) -> Decimal:
        """Calcula o valor global proposto: (mensal) * (duração em meses)."""
        rule = cls.get_funding_rule(edital, target_group)
        months = duration_months if duration_months is not None else rule.duration_months
        monthly_total = cls.calculate_monthly_value(edital, target_group, vacancies)
        return monthly_total * Decimal(months)

    @classmethod
    def calculate_minimum_equity(
        cls,
        edital: Edital,
        target_group: str,
        valor_global: Decimal,
    ) -> Decimal:
        """Calcula o patrimônio líquido mínimo exigido com base no percentual configurado."""
        rule = cls.get_funding_rule(edital, target_group)
        percentage = rule.minimum_equity_percentage
        if percentage <= Decimal("0.00"):
            return Decimal("0.00")
        return (valor_global * percentage) / Decimal("100.00")

    @classmethod
    def validate_equity_adequacy(
        cls,
        edital: Edital,
        target_group: str,
        valor_global: Decimal,
        patrimonio_declarado: Decimal,
    ) -> bool:
        """Verifica se o patrimônio líquido da entidade é suficiente frente ao valor global."""
        minimo = cls.calculate_minimum_equity(edital, target_group, valor_global)
        return patrimonio_declarado >= minimo
