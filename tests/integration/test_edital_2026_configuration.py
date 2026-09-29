from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.edital_2026 import configuration_fingerprint, configure_edital_2026_base
from apps.editais.models import Edital, ProgramMunicipality, RequirementValidationRule
from apps.editais.services import EditalConfigurationService
from apps.evaluations.validation_rules import ValidationRuleEvaluator
from apps.institutions.models import Institution, Municipality
from apps.ranking.services import ClassificationService
from apps.submissions.models import Submission
from apps.submissions.services.duplicates import DuplicateService
from apps.submissions.services.identity import SubmissionIdentityService


@pytest.fixture
def edital_2026(db):
    now = timezone.now()
    admin = User.objects.create_user(username="admin-2026-config", role=User.Role.ADMINISTRADOR)
    User.objects.create_user(username="analyst-2026-config", role=User.Role.ANALISTA)
    User.objects.create_user(username="reviewer-2026-config", role=User.Role.REVISOR)
    edital = Edital.objects.create(
        name="Edital 2026",
        number="26-TEMPLATE",
        year=2026,
        opens_at=now,
        closes_at=now + timedelta(days=180),
        validation_reference_date=date(2026, 6, 30),
        requires_financial_rules=False,
    )
    program = configure_edital_2026_base(edital, admin)
    municipality = Municipality.objects.create(name="São Paulo", state="SP", ibge_code="3550308")
    ProgramMunicipality.objects.create(
        edital=edital,
        program=program,
        program_name=program.code,
        municipality=municipality,
    )
    return {"admin": admin, "edital": edital, "program": program, "municipality": municipality}


@pytest.mark.django_db
def test_2026_template_fingerprint_and_conditional_check(edital_2026):
    edital = edital_2026["edital"]
    assert configuration_fingerprint() == {"requirements": 14, "checks": 23}
    assert edital.requirements.filter(active=True).count() == 14
    assert sum(req.checks.filter(active=True).count() for req in edital.requirements.all()) == 23
    proof = edital.requirements.get(code="ANEXO_III").checks.get(code="COMPROVACAO_AUTODECLARADA")
    assert proof.required
    assert "NAO_APLICAVEL" in proof.allowed_statuses
    assert "NAO_APLICAVEL" in proof.accepted_statuses
    validation = EditalConfigurationService.validate(edital)
    assert validation["can_publish"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("female", "male", "nursing", "in_program", "expected"),
    [
        (4, 0, 0, False, "G1"),
        (4, 3, 0, False, "G1"),
        (0, 0, 2, False, "G1"),
        (0, 3, 0, True, "G2"),
        (0, 3, 0, False, "G3"),
        (0, 0, 0, False, "SEM_GRUPO"),
    ],
)
def test_2026_classification_policy_boundaries(
    edital_2026, female, male, nursing, in_program, expected
):
    context = edital_2026
    institution = Institution.objects.create(
        name=f"Instituição {female}-{male}-{nursing}-{in_program}",
        cnpj="00000000000191",
    )
    municipality = context["municipality"]
    if not in_program:
        municipality = Municipality.objects.create(
            name=f"Município {female}-{male}-{nursing}", state="MG"
        )
    submission = Submission.objects.create(
        edital=context["edital"],
        institution=institution,
        processo_sei=f"CASE-{female}-{male}-{nursing}-{in_program}",
        received_at=timezone.now(),
        municipality=municipality,
        vagas_femininas=female,
        vagas_masculinas=male,
        vagas_maes_nutrizes=nursing,
    )
    assert ClassificationService.classify_submission(submission) == expected


@pytest.mark.django_db
def test_2026_typed_validators_use_canonical_cnpj_and_reference_date(edital_2026):
    edital = edital_2026["edital"]
    institution = Institution.objects.create(name="OSC Validator", cnpj="00000000000191")
    submission = SimpleNamespace(edital=edital, institution=institution)
    evaluation = SimpleNamespace(submission=submission)
    cnpj_check = edital.requirements.get(code="ENDERECO_ENTIDADE").checks.get()
    cnpj_rule = cnpj_check.validation_rules.get(
        rule_type=RequirementValidationRule.RuleType.CNPJ_MATCH_CANONICAL
    )
    result = SimpleNamespace(
        evaluation=evaluation,
        requirement_check_id=cnpj_check.pk,
        requirement_check=cnpj_check,
        document_cnpj="00000000000191",
        canonical_cnpj_confirmed=False,
        opened_on=None,
        valid_until=None,
        cnae="",
    )
    assert ValidationRuleEvaluator.evaluate_rule(cnpj_rule, result).status == "PASS"
    result.document_cnpj = "11222333000181"
    outcome = ValidationRuleEvaluator.evaluate_rule(cnpj_rule, result)
    assert outcome.status == "FAIL"
    assert outcome.actual == "11222333000181"
    assert outcome.expected == institution.cnpj

    anexo_check = edital.requirements.get(code="ANEXO_I").checks.get()
    anexo_rule = anexo_check.validation_rules.get(
        rule_type=RequirementValidationRule.RuleType.CNPJ_MATCH_CANONICAL
    )
    anexo_result = SimpleNamespace(
        evaluation=evaluation,
        requirement_check_id=anexo_check.pk,
        requirement_check=anexo_check,
        document_cnpj="11222333000181",
        canonical_cnpj_confirmed=False,
        opened_on=None,
        valid_until=None,
        cnae="",
    )
    assert ValidationRuleEvaluator.evaluate_rule(anexo_rule, anexo_result).status == "FAIL"
    anexo_result.document_cnpj = institution.cnpj
    assert ValidationRuleEvaluator.evaluate_rule(anexo_rule, anexo_result).status == "PENDING"
    anexo_result.canonical_cnpj_confirmed = True
    assert ValidationRuleEvaluator.evaluate_rule(anexo_rule, anexo_result).status == "PASS"

    age_check = edital.requirements.get(code="CNPJ_ENTIDADE").checks.get()
    age_rule = age_check.validation_rules.get(
        rule_type=RequirementValidationRule.RuleType.CNPJ_MINIMUM_AGE
    )
    for opened, expected in [
        (date(2023, 7, 1), "FAIL"),  # Two years and 364 days on the reference date.
        (date(2023, 6, 30), "PASS"),
        (date(2022, 1, 1), "PASS"),
        (date(2027, 1, 1), "FAIL"),
        (None, "PENDING"),
    ]:
        result.opened_on = opened
        assert ValidationRuleEvaluator.evaluate_rule(age_rule, result).status == expected

    sicaf = edital.requirements.get(code="SICAF").checks.get()
    date_rule = sicaf.validation_rules.get(
        rule_type=RequirementValidationRule.RuleType.DATE_NOT_EXPIRED
    )
    result.valid_until = date(2026, 6, 29)
    assert ValidationRuleEvaluator.evaluate_rule(date_rule, result).status == "FAIL"
    result.valid_until = date(2026, 6, 30)
    assert ValidationRuleEvaluator.evaluate_rule(date_rule, result).status == "PASS"
    result.valid_until = None
    assert ValidationRuleEvaluator.evaluate_rule(date_rule, result).status == "PENDING"

    cnae_check = age_check
    cnae_rule = cnae_check.validation_rules.get(
        rule_type=RequirementValidationRule.RuleType.CNAE_REQUIRED
    )
    result.cnae = "87.20-4-99"
    assert ValidationRuleEvaluator.evaluate_rule(cnae_rule, result).status == "UNRESOLVED"
    cnae_rule.config = {"expected_cnae": "87.20-4-99", "match_mode": "EXACT"}
    assert ValidationRuleEvaluator.evaluate_rule(cnae_rule, result).status == "PASS"
    cnae_rule.config = {"expected_cnae": "87.20-4-99", "match_mode": "CONTAINS"}
    result.cnae = "62.01-5-01; 87.20-4-99"
    assert ValidationRuleEvaluator.evaluate_rule(cnae_rule, result).status == "PASS"
    result.cnae = "62.01-5-01"
    assert ValidationRuleEvaluator.evaluate_rule(cnae_rule, result).status == "FAIL"


@pytest.mark.django_db
def test_publication_requires_reference_date_for_active_date_rules(edital_2026):
    edital = edital_2026["edital"]
    edital.validation_reference_date = None
    result = EditalConfigurationService.validate(edital)
    assert not result["can_publish"]
    assert any("data oficial de referência" in message for message in result["errors"])


@pytest.mark.django_db
def test_mothers_g1_configuration_is_editable_and_not_a_global_enum(edital_2026):
    edital = edital_2026["edital"]
    assert list(edital.target_groups.order_by("order").values_list("code", flat=True)) == [
        "G1",
        "G2",
        "G3",
    ]
    g1 = edital.target_groups.get(code="G1")
    assert g1.vacancy_types == ["FEMALE", "NURSING_MOTHER"]
    g1.vacancy_types = ["FEMALE"]
    g1.save()
    assert "NURSING_MOTHER" not in edital.target_groups.get(code="G1").vacancy_types


@pytest.mark.django_db
def test_new_edital_duplicate_default_warns_without_suppressing(edital_2026):
    edital = edital_2026["edital"]
    institution = Institution.objects.create(name="Duplicate candidate", cnpj="00000000000191")
    candidates = [
        Submission.objects.create(
            edital=edital,
            institution=institution,
            processo_sei=f"DUP-{index}",
            received_at=timezone.now() + timedelta(minutes=index),
            vagas_femininas=1,
        )
        for index in (1, 2)
    ]
    result = DuplicateService.resolve_duplicates(
        iter(candidates), policy=Edital.DuplicatePolicy.WARN_ONLY
    )
    assert result.retained == candidates
    assert result.suppressed == []
    assert result.suppression_reasons == {}


@pytest.mark.django_db
def test_cnpj_correction_is_per_submission_and_audited(edital_2026):
    context = edital_2026
    actor = context["admin"]
    original = Institution.objects.create(name="CNPJ antigo", cnpj="00000000000191")
    other_submission = Submission.objects.create(
        edital=context["edital"],
        institution=original,
        processo_sei="KEEP-OLD-CNPJ",
        received_at=timezone.now(),
    )
    corrected_submission = Submission.objects.create(
        edital=context["edital"],
        institution=original,
        processo_sei="CORRECT-CNPJ",
        received_at=timezone.now(),
    )
    corrected = SubmissionIdentityService.correct_cnpj(
        corrected_submission,
        "11222333000181",
        "CNPJ digitado incorretamente; conferido contra Anexo I.",
        actor,
    )
    other_submission.refresh_from_db()
    corrected.refresh_from_db()
    assert other_submission.institution_id == original.pk
    assert corrected.institution.cnpj == "11222333000181"
    event = AuditEvent.objects.get(action="CANONICAL_CNPJ_CORRECTION")
    assert event.actor == actor
    assert event.old_value == "00000000000191"
    assert event.new_value == "11222333000181"
    assert "Anexo I" in event.metadata["reason"]


@pytest.mark.django_db
def test_cnpj_correction_rejects_invalid_values(edital_2026):

    institution = Institution.objects.create(name="CNPJ antigo", cnpj="00000000000191")
    submission = Submission.objects.create(
        edital=edital_2026["edital"],
        institution=institution,
        processo_sei="CORRECT-INVALID",
        received_at=timezone.now(),
    )
    with pytest.raises(ValidationError):
        SubmissionIdentityService.correct_cnpj(
            submission, "00000000000199", "Justificativa suficiente", edital_2026["admin"]
        )


@pytest.mark.django_db
def test_seed_command_creates_unpublished_excel_independent_base():
    admin = User.objects.create_user(username="seed-admin", role=User.Role.ADMINISTRADOR)
    call_command(
        "seed_edital_2026_base",
        admin="seed-admin",
        number="2026-SEED-TEST",
        opens_at="2026-01-01T09:00:00-03:00",
        closes_at="2026-12-31T18:00:00-03:00",
    )
    edital = Edital.objects.get(number="2026-SEED-TEST", year=2026)
    assert edital.status == Edital.Status.DRAFT
    assert edital.validation_reference_date is None
    assert edital.requirements.filter(active=True).count() == 14
    assert AuditEvent.objects.filter(
        actor=admin,
        entity_type="Edital",
        entity_id=str(edital.pk),
        action="CONFIG_CREATE",
    ).exists()


@pytest.mark.django_db
def test_only_admin_or_coordinator_can_correct_cnpj(client, edital_2026):
    analyst = User.objects.create_user(username="analyst-no-correction", role=User.Role.ANALISTA)
    institution = Institution.objects.create(name="Original OSC", cnpj="00000000000191")
    submission = Submission.objects.create(
        edital=edital_2026["edital"],
        institution=institution,
        processo_sei="CORRECT-IDOR",
        received_at=timezone.now(),
    )
    client.force_login(analyst)
    from django.urls import reverse

    response = client.post(
        reverse("submission-cnpj-correction", args=[submission.pk]),
        {"cnpj": "11222333000181", "reason": "Correção não autorizada por analista."},
    )
    assert response.status_code == 403
    submission.refresh_from_db()
    assert submission.institution.cnpj == "00000000000191"
    assert not AuditEvent.objects.filter(action="CANONICAL_CNPJ_CORRECTION").exists()
