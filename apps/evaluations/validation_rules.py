import re
from dataclasses import dataclass

from apps.editais.models import RequirementValidationRule
from apps.institutions.cnpj import normalize_cnpj


@dataclass(frozen=True)
class ValidationOutcome:
    rule: RequirementValidationRule
    status: str
    message: str
    actual: str = ""
    expected: str = ""


def _add_years(value, years):
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        # February 29 reaches February 28 in a non-leap target year.
        return value.replace(month=2, day=28, year=value.year + years)


def _normalize_cnae(value):
    return re.sub(r"[^0-9]", "", value or "")


class ValidationRuleEvaluator:
    """Evaluates the four supported declarative rules; never executes stored code."""

    @classmethod
    def evaluate_rule(cls, rule, result):
        config = rule.config if isinstance(rule.config, dict) else {}
        edital = result.evaluation.submission.edital
        reference = edital.validation_reference_date
        kind = rule.rule_type
        if kind == RequirementValidationRule.RuleType.CNPJ_MATCH_CANONICAL:
            expected = normalize_cnpj(result.evaluation.submission.institution.cnpj)
            actual = normalize_cnpj(result.document_cnpj)
            if rule.requirement_check.collect_document_cnpj:
                if not actual:
                    return ValidationOutcome(
                        rule, "PENDING", "Informe o CNPJ declarado no documento.", "", expected
                    )
                if actual != expected:
                    return ValidationOutcome(
                        rule,
                        "FAIL",
                        "CNPJ do documento diverge do CNPJ da candidatura.",
                        result.document_cnpj,
                        result.evaluation.submission.institution.cnpj,
                    )
            if rule.requirement_check.collect_canonical_cnpj_confirmed:
                if not result.canonical_cnpj_confirmed:
                    return ValidationOutcome(
                        rule,
                        "PENDING",
                        "Confirme o CNPJ da candidatura declarado no Anexo I.",
                        actual,
                        expected,
                    )
                return ValidationOutcome(
                    rule,
                    "PASS",
                    "CNPJ da candidatura, declarado no Anexo I, confirmado pelo analista.",
                    actual or expected,
                    expected,
                )
            if actual == expected:
                return ValidationOutcome(
                    rule, "PASS", "CNPJ corresponde à candidatura.", actual, expected
                )
            return ValidationOutcome(rule, "PENDING", "Informe o CNPJ do documento.", "", expected)
        if kind == RequirementValidationRule.RuleType.DATE_NOT_EXPIRED:
            if reference is None:
                return ValidationOutcome(rule, "PENDING", "Configure a data de referência.")
            if result.valid_until is None:
                return ValidationOutcome(rule, "PENDING", "SEM DATA: informe a validade.")
            if result.valid_until < reference:
                return ValidationOutcome(
                    rule,
                    "FAIL",
                    f"Documento vencido em {result.valid_until:%d/%m/%Y}.",
                    str(result.valid_until),
                    str(reference),
                )
            return ValidationOutcome(
                rule,
                "PASS",
                f"Documento vigente em {reference:%d/%m/%Y}.",
                str(result.valid_until),
                str(reference),
            )
        if kind == RequirementValidationRule.RuleType.CNPJ_MINIMUM_AGE:
            if reference is None:
                return ValidationOutcome(rule, "PENDING", "Configure a data de referência.")
            if result.opened_on is None:
                return ValidationOutcome(rule, "PENDING", "Informe a data de abertura do CNPJ.")
            years = config.get("years")
            if result.opened_on > reference:
                return ValidationOutcome(
                    rule, "FAIL", "Data de abertura posterior à data de referência."
                )
            expected_date = _add_years(result.opened_on, years)
            if expected_date > reference:
                return ValidationOutcome(
                    rule,
                    "FAIL",
                    f"CNPJ não completou {years} anos na data de referência.",
                    str(result.opened_on),
                    str(reference),
                )
            return ValidationOutcome(
                rule,
                "PASS",
                f"CNPJ completou ao menos {years} anos.",
                str(result.opened_on),
                str(reference),
            )
        if kind == RequirementValidationRule.RuleType.CNAE_REQUIRED:
            actual = (result.cnae or "").strip()
            expected = config.get("expected_cnae", "")
            mode = config.get("match_mode")
            if not actual:
                return ValidationOutcome(rule, "PENDING", "Informe o CNAE.", actual, expected)
            if mode == "UNRESOLVED":
                return ValidationOutcome(
                    rule,
                    "UNRESOLVED",
                    "A comparação do CNAE depende de decisão da coordenação.",
                    actual,
                    expected,
                )
            if mode == "EXACT":
                matches = _normalize_cnae(actual) == _normalize_cnae(expected)
            elif mode == "CONTAINS":
                tokens = re.split(r"[,;|/]+", actual)
                matches = _normalize_cnae(expected) in {_normalize_cnae(token) for token in tokens}
            else:
                return ValidationOutcome(rule, "PENDING", "Configure o modo de comparação do CNAE.")
            return ValidationOutcome(
                rule,
                "PASS" if matches else "FAIL",
                "CNAE corresponde ao esperado." if matches else "CNAE não corresponde ao esperado.",
                actual,
                expected,
            )
        return ValidationOutcome(rule, "PENDING", "Tipo de validação não suportado.")

    @classmethod
    def evaluate_result(cls, result):
        rules = (
            [rule for rule in result.requirement_check.validation_rules.all() if rule.active]
            if result.requirement_check_id
            else RequirementValidationRule.objects.none()
        )
        return [cls.evaluate_rule(rule, result) for rule in rules]

    @classmethod
    def evaluate_evaluation(cls, evaluation):
        return [
            outcome
            for result in evaluation.check_results.select_related(
                "evaluation__submission__edital", "evaluation__submission__institution"
            ).prefetch_related("requirement_check__validation_rules")
            for outcome in cls.evaluate_result(result)
        ]

    @classmethod
    def blockers(cls, evaluation):
        return [
            outcome
            for outcome in cls.evaluate_evaluation(evaluation)
            if outcome.rule.blocks_completion
            and outcome.rule.severity == RequirementValidationRule.Severity.CRITICAL
            and outcome.status != "PASS"
        ]
