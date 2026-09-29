from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.editais.models import RequirementValidationRule
from apps.editais.services import EditalConfigurationService

RULES = [
    ("DATE_NOT_EXPIRED", "collect_valid_until", {"reference_date": "EDITAL_REFERENCE_DATE"}),
    ("CNPJ_MATCH_CANONICAL", "collect_document_cnpj", {}),
    (
        "CNPJ_MINIMUM_AGE",
        "collect_opened_on",
        {"reference_date": "EDITAL_REFERENCE_DATE", "years": 3},
    ),
    ("CNAE_REQUIRED", "collect_cnae", {"expected_cnae": "87.20-4-99", "match_mode": "EXACT"}),
]


@pytest.mark.django_db
@pytest.mark.parametrize("kind,flag,config", RULES)
def test_validator_required_evidence_blocks_publication(domain, kind, flag, config):
    edital = domain["edital"]
    edital.validation_reference_date = date(2026, 6, 30)
    edital.save()
    check = domain["check"]
    rule = RequirementValidationRule.objects.create(
        requirement_check=check, rule_type=kind, config=config
    )
    with pytest.raises(ValidationError, match="exige.*campo"):
        rule.full_clean()
    validation = EditalConfigurationService.validate(edital)
    assert not validation["can_publish"]
    assert any("exige" in message for message in validation["errors"])
    with pytest.raises(ValidationError, match="exige"):
        EditalConfigurationService.publish(edital, domain["admin"])
    setattr(check, flag, True)
    check.save()
    rule.requirement_check = check
    rule.full_clean()
    assert not any(
        "exige" in message for message in EditalConfigurationService.validate(edital)["errors"]
    )


@pytest.mark.django_db
def test_inactive_validator_does_not_block_missing_parameters_or_evidence(domain):
    rule = RequirementValidationRule.objects.create(
        requirement_check=domain["check"], rule_type="CNPJ_MINIMUM_AGE", config={}, active=False
    )
    rule.full_clean()
    assert not any(
        "years" in message or "exige" in message
        for message in EditalConfigurationService.validate(domain["edital"])["errors"]
    )


@pytest.mark.django_db
def test_validator_parameters_still_required(domain):
    domain["check"].collect_opened_on = True
    domain["check"].save()
    rule = RequirementValidationRule.objects.create(
        requirement_check=domain["check"],
        rule_type="CNPJ_MINIMUM_AGE",
        config={"reference_date": "EDITAL_REFERENCE_DATE"},
    )
    with pytest.raises(ValidationError, match="years"):
        rule.full_clean()


@pytest.mark.django_db
def test_validator_form_rejects_inaccessible_field(client, domain):
    client.force_login(domain["admin"])
    response = client.post(
        reverse("edital-section-create", args=[domain["edital"].pk, "validacoes"]),
        {
            "requirement_check": domain["check"].pk,
            "rule_type": "DATE_NOT_EXPIRED",
            "active": "on",
            "severity": "CRITICAL",
            "blocks_completion": "on",
        },
    )
    assert response.status_code == 200
    assert "Validade" in response.content.decode()
    assert not RequirementValidationRule.objects.exists()
