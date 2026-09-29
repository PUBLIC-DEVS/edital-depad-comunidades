"""Decimal financial calculations by vacancy type, with explicit cent rounding."""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from apps.editais.models import FundingRule


class FundingRuleNotFoundError(Exception):
    pass


class FundingService:
    @staticmethod
    def get_funding_rule(edital, vacancy_type):
        rule = FundingRule.objects.filter(edital=edital, vacancy_type=vacancy_type).first()
        if rule is None:
            raise FundingRuleNotFoundError(f"Missing rule for {vacancy_type}")
        return rule

    @classmethod
    def calculate_monthly_value(cls, edital, vacancy_type, vacancies):
        if vacancies < 0 or int(vacancies) != vacancies:
            raise ValidationError("Vagas devem ser inteiras e não negativas.")
        return cls.get_funding_rule(edital, vacancy_type).monthly_value * Decimal(vacancies)

    @classmethod
    def calculate_global_value(cls, edital, vacancy_type, vacancies, duration_months=None):
        rule = cls.get_funding_rule(edital, vacancy_type)
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
        amounts = [
            (FundingRule.VacancyType.FEMALE, submission.vagas_femininas),
            (FundingRule.VacancyType.MALE, submission.vagas_masculinas),
            (FundingRule.VacancyType.NURSING_MOTHER, submission.vagas_maes_nutrizes),
        ]
        total = sum(
            (cls.calculate_global_value(submission.edital, t, n) for t, n in amounts if n),
            Decimal(0),
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return total, cls.calculate_minimum_equity(submission.edital, total)

    @classmethod
    def validate_equity_adequacy(cls, edital, valor_global, patrimonio_declarado):
        return patrimonio_declarado >= cls.calculate_minimum_equity(edital, valor_global)
