"""Decimal financial calculations by vacancy type, with explicit cent rounding."""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.editais.models import FundingRule


class FundingRuleNotFoundError(Exception):
    pass


class FundingService:
    @staticmethod
    def get_funding_rule(edital, vacancy_type, as_of=None):
        rule = FundingRule.objects.filter(edital=edital, vacancy_type=vacancy_type).first()
        if rule is None:
            raise FundingRuleNotFoundError(f"Missing rule for {vacancy_type}")
        if as_of and (
            (rule.valid_from and as_of < rule.valid_from)
            or (rule.valid_until and as_of > rule.valid_until)
        ):
            raise ValidationError(
                f"Regra financeira para {vacancy_type} fora da vigência na data de recebimento."
            )
        return rule

    @classmethod
    def calculate_monthly_value(cls, edital, vacancy_type, vacancies):
        if vacancies < 0 or int(vacancies) != vacancies:
            raise ValidationError("Vagas devem ser inteiras e não negativas.")
        return cls.get_funding_rule(edital, vacancy_type).monthly_value * Decimal(vacancies)

    @classmethod
    def calculate_global_value(
        cls, edital, vacancy_type, vacancies, duration_months=None, as_of=None
    ):
        rule = cls.get_funding_rule(edital, vacancy_type, as_of)
        months = rule.duration_months if duration_months is None else duration_months
        if months <= 0:
            raise ValidationError("Duração deve ser positiva.")
        return (
            cls.calculate_monthly_value(edital, vacancy_type, vacancies) * Decimal(months)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate_minimum_equity(edital, valor_global):
        return (valor_global * edital.minimum_equity_percentage / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @classmethod
    def calculate_submission_values(cls, submission):
        if not submission.edital.requires_financial_rules:
            return None, None
        amounts = [
            (FundingRule.VacancyType.FEMALE, submission.vagas_femininas),
            (FundingRule.VacancyType.MALE, submission.vagas_masculinas),
            (FundingRule.VacancyType.NURSING_MOTHER, submission.vagas_maes_nutrizes),
        ]
        total = sum(
            (
                cls.calculate_global_value(
                    submission.edital,
                    t,
                    n,
                    as_of=timezone.localdate(submission.received_at)
                    if submission.received_at
                    else None,
                )
                for t, n in amounts
                if n
            ),
            Decimal(0),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return total, cls.calculate_minimum_equity(submission.edital, total)

    @classmethod
    def validate_equity_adequacy(cls, edital, valor_global, patrimonio_declarado):
        return patrimonio_declarado >= cls.calculate_minimum_equity(edital, valor_global)
