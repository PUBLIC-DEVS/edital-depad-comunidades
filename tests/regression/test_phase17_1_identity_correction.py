import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.editais.models import RequirementValidationRule
from apps.evaluations.models import Evaluation
from apps.evaluations.services import EvaluationService
from apps.evaluations.validation_rules import ValidationRuleEvaluator
from apps.submissions.models import ParticipationRestriction, Submission
from apps.submissions.services.identity import SubmissionIdentityService


@pytest.fixture
def identity_case(domain):
    check = domain["check"]
    check.collect_document_cnpj = True
    check.collect_canonical_cnpj_confirmed = True
    check.save()
    RequirementValidationRule.objects.create(
        requirement_check=check, rule_type="CNPJ_MATCH_CANONICAL"
    )
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    result = evaluation.check_results.get()
    result.document_cnpj = "11222333000181"
    result.status = "ATENDE"
    result.canonical_cnpj_confirmed = True
    result.save()
    return domain, evaluation, result


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role,allowed",
    [
        ("admin", True),
        ("coord", True),
        ("distributor", False),
        ("analyst", False),
        ("reviewer", False),
        ("consulta", False),
    ],
)
def test_identity_correction_http_roles_and_confirmation(client, identity_case, role, allowed):
    domain, evaluation, result = identity_case
    client.force_login(domain[role])
    url = reverse("submission-cnpj-correction", args=[domain["sub"].pk])
    assert client.get(url).status_code == (405 if allowed else 403)
    domain["sub"].refresh_from_db()
    assert domain["sub"].institution.cnpj == "00000000000191"
    response = client.post(
        url, {"cnpj": "11222333000181", "reason": "Conferido no Anexo I.", "confirm": "on"}
    )
    assert response.status_code == (302 if allowed else 403)
    domain["sub"].refresh_from_db()
    assert domain["sub"].institution.cnpj == ("11222333000181" if allowed else "00000000000191")
    assert Evaluation.objects.count() == 1
    assert evaluation.check_results.count() == 1
    result.refresh_from_db()
    assert result.document_cnpj == "11222333000181"
    assert result.status == "ATENDE"
    if allowed:
        assert not result.canonical_cnpj_confirmed
        event = AuditEvent.objects.get(action="CANONICAL_CNPJ_CORRECTION")
        assert event.old_value == "00000000000191"
        assert event.new_value == "11222333000181"
        assert event.actor == domain[role]
        assert AuditEvent.objects.filter(action="IDENTITY_VALIDATIONS_REEVALUATED").exists()


@pytest.mark.django_db
def test_identity_correction_preserves_shared_institution_and_revalidates(identity_case):
    domain, evaluation, result = identity_case
    old = domain["sub"].institution
    other = Submission.objects.create(
        edital=domain["edital"],
        institution=old,
        processo_sei="OTHER",
        received_at=domain["sub"].received_at,
    )
    rule = result.requirement_check.validation_rules.get()
    assert ValidationRuleEvaluator.evaluate_rule(rule, result).status == "FAIL"
    corrected = SubmissionIdentityService.correct_cnpj(
        domain["sub"], "11222333000181", "Anexo I conferido.", domain["coord"]
    )
    other.refresh_from_db()
    assert other.institution_id == old.pk
    old.refresh_from_db()
    assert old.cnpj == "00000000000191"
    result.refresh_from_db()
    result.canonical_cnpj_confirmed = True
    assert ValidationRuleEvaluator.evaluate_rule(rule, result).status == "PASS"
    assert corrected.workflow_status == "UNDER_ANALYSIS"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cnpj,reason", [("00000000000199", "Justificativa"), ("11222333000181", "")]
)
def test_identity_correction_invalid_input_is_atomic(identity_case, cnpj, reason):
    domain, _, _ = identity_case
    with pytest.raises(ValidationError):
        SubmissionIdentityService.correct_cnpj(domain["sub"], cnpj, reason, domain["admin"])
    domain["sub"].refresh_from_db()
    assert domain["sub"].institution.cnpj == "00000000000191"
    assert not AuditEvent.objects.filter(action="CANONICAL_CNPJ_CORRECTION").exists()


@pytest.mark.django_db
def test_identity_correction_requires_http_confirmation(client, identity_case):
    domain, _, _ = identity_case
    client.force_login(domain["admin"])
    client.post(
        reverse("submission-cnpj-correction", args=[domain["sub"].pk]),
        {"cnpj": "11222333000181", "reason": "Conferido no Anexo I."},
    )
    domain["sub"].refresh_from_db()
    assert domain["sub"].institution.cnpj == "00000000000191"


@pytest.mark.django_db
def test_identity_correction_cannot_bypass_active_restriction(identity_case):
    domain, _, _ = identity_case
    ParticipationRestriction.objects.create(
        edital=domain["edital"],
        cnpj="11222333000181",
        reason="Vedado",
        source="Teste",
        created_by=domain["admin"],
    )
    with pytest.raises(ValidationError, match="restrição ativa"):
        SubmissionIdentityService.correct_cnpj(
            domain["sub"], "11222333000181", "Conferido no Anexo I.", domain["admin"]
        )
    domain["sub"].refresh_from_db()
    assert domain["sub"].institution.cnpj == "00000000000191"


@pytest.mark.django_db
def test_identity_correction_protects_completed_decisions(identity_case):
    domain, evaluation, _ = identity_case
    evaluation.status = "COMPLETED"
    evaluation.save()
    with pytest.raises(ValidationError, match="rascunho"):
        SubmissionIdentityService.correct_cnpj(
            domain["sub"], "11222333000181", "Conferido no Anexo I.", domain["admin"]
        )


@pytest.mark.django_db
def test_identity_reuses_existing_institution_and_records_duplicate(identity_case):
    from apps.institutions.models import Institution

    domain, _, _ = identity_case
    target = Institution.objects.create(cnpj="11222333000181", name="Instituição correta")
    duplicate = Submission.objects.create(
        edital=domain["edital"],
        institution=target,
        processo_sei="SAME-NEW-CNPJ",
        received_at=domain["sub"].received_at,
    )
    corrected = SubmissionIdentityService.correct_cnpj(
        domain["sub"], target.cnpj, "Conferido no Anexo I.", domain["coord"]
    )
    assert corrected.institution_id == target.pk
    event = AuditEvent.objects.get(action="CANONICAL_CNPJ_CORRECTION")
    assert event.metadata["duplicate_submission_ids"] == [duplicate.pk]
    assert corrected.workflow_status == "UNDER_ANALYSIS"


@pytest.mark.django_db
def test_identity_recovery_action_visible_after_start_and_detail_get_is_safe(client, identity_case):
    domain, evaluation, result = identity_case
    client.force_login(domain["coord"])
    before = AuditEvent.objects.count()
    response = client.get(reverse("submission-detail", args=[domain["sub"].pk]))
    assert response.status_code == 200
    assert "Corrigir CNPJ da candidatura" in response.content.decode()
    assert AuditEvent.objects.count() == before
    assert Evaluation.objects.count() == 1
    result.refresh_from_db()
    assert result.canonical_cnpj_confirmed
