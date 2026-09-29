import csv
import io
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.editais.models import ProgramMunicipality
from apps.editais.services import EditalConfigurationService
from apps.submissions.models import Assignment, ParticipationRestriction, Submission
from apps.submissions.services.eligibility import ParticipationEligibilityService as Eligibility
from apps.submissions.services.validation import SubmissionAnomalyDetector
from apps.submissions.services.workflow import WorkflowService


def block(domain):
    sub = domain["sub"]
    sub.workflow_status = "RECEIVED"
    sub.save(update_fields=["workflow_status"])
    restriction = ParticipationRestriction(
        edital=domain["edital"],
        cnpj=sub.institution.cnpj,
        reason="Contrato ativo",
        source="Teste",
        reference_period="Informado",
    )
    Eligibility.create_restriction(restriction, domain["admin"])
    sub.refresh_from_db()
    return restriction


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["normal", "restricted", "duplicate"])
def test_intake_manual_csv_same_screening(client, domain, kind):
    edital = domain["edital"]
    edital.requires_financial_rules = False
    edital.closes_at = edital.opens_at + timedelta(days=30)
    edital.save()
    ProgramMunicipality.objects.create(
        edital=edital,
        program=edital.target_groups.get(code="G2").program,
        program_name="PRONASCI",
        municipality=domain["sub"].municipality,
    )
    EditalConfigurationService.publish(edital, domain["admin"])
    cnpj = domain["sub"].institution.cnpj if kind == "duplicate" else "11222333000181"
    name = domain["sub"].institution.name if kind == "duplicate" else "Nova entidade"
    if kind == "restricted":
        Eligibility.create_restriction(
            ParticipationRestriction(
                edital=edital, cnpj=cnpj, reason="Contrato ativo", source="Teste"
            ),
            domain["admin"],
        )
    client.force_login(domain["distributor"])
    data = {
        "edital": edital.pk,
        "municipality": domain["sub"].municipality_id,
        "processo_sei": "MANUAL",
        "received_at": "2026-06-01T10:00",
        "institution_cnpj": cnpj,
        "institution_name": name,
        "vagas_femininas": 0,
        "vagas_masculinas": 2,
        "vagas_maes_nutrizes": 0,
        "vagas_solicitadas": 2,
        "capacidade_total": 10,
    }
    response = client.post(reverse("submission-create"), data)
    assert response.status_code == 302
    row = {
        "processo_sei": "CSV",
        "recebido_em": data["received_at"],
        "cnpj": cnpj,
        "instituicao": name,
        "ibge": domain["sub"].municipality.ibge_code,
        "vagas_femininas": 0,
        "vagas_masculinas": 2,
        "vagas_maes_nutrizes": 0,
        "vagas_solicitadas": 2,
        "capacidade_total": 10,
    }
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=row)
    writer.writeheader()
    writer.writerow(row)
    response = client.post(
        reverse("submission-import-csv"),
        {"edital": edital.pk, "file": SimpleUploadedFile("input.csv", stream.getvalue().encode())},
    )
    assert response.status_code == 302, response.content.decode()
    manual, imported = [Submission.objects.get(processo_sei=sei) for sei in ("MANUAL", "CSV")]
    assert (
        manual.workflow_status
        == imported.workflow_status
        == ("INELIGIBLE" if kind == "restricted" else "RECEIVED")
    )
    assert manual.target_group == imported.target_group
    assert Eligibility.is_restricted(manual) == Eligibility.is_restricted(imported)
    assert {a.code for a in SubmissionAnomalyDetector.check_submission(manual)} == {
        a.code for a in SubmissionAnomalyDetector.check_submission(imported)
    }
    assert AuditEvent.objects.filter(entity_type="Submission", action="CREATE_CSV").exists()


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
def test_restriction_release_roles_and_get_safety(client, domain, role, allowed):
    restriction = block(domain)
    restriction.active = False
    Eligibility.update_restriction(restriction, domain["admin"])
    domain["sub"].refresh_from_db()
    assert domain["sub"].workflow_status == "INELIGIBLE"
    client.force_login(domain[role])
    url = reverse("submission-restriction-release", args=[domain["sub"].pk])
    assert client.get(url).status_code == (405 if allowed else 403)
    response = client.post(url, {"reason": "Fonte desativada após conferência.", "confirm": "on"})
    assert response.status_code == (302 if allowed else 403)
    domain["sub"].refresh_from_db()
    assert domain["sub"].workflow_status == ("RECEIVED" if allowed else "INELIGIBLE")
    assert not domain["sub"].assignments.filter(status="ACTIVE").exists()
    if allowed:
        assert AuditEvent.objects.filter(
            action="RELEASE_PREANALYSIS_BLOCK", actor=domain[role]
        ).exists()
        WorkflowService.assign_analyst(domain["sub"], domain["analyst"], domain["distributor"])
        domain["sub"].refresh_from_db()
        assert domain["sub"].workflow_status == "ASSIGNED"
        assert domain["sub"].assignments.filter(status="ACTIVE").count() == 1


@pytest.mark.django_db
def test_restriction_release_rejects_remaining_source_and_assignment(domain):
    restriction = block(domain)
    with pytest.raises(ValidationError, match="restrição ativa"):
        Eligibility.release_preanalysis_block(domain["sub"], domain["coord"], "Conferido")
    with pytest.raises((PermissionDenied, ValidationError)):
        WorkflowService.assign_analyst(domain["sub"], domain["analyst"], domain["distributor"])
    restriction.active = False
    Eligibility.update_restriction(restriction, domain["admin"])
    with pytest.raises(ValidationError, match="estágio"):
        WorkflowService.assign_analyst(domain["sub"], domain["analyst"], domain["distributor"])
    with pytest.raises(ValidationError, match="justificativa"):
        Eligibility.release_preanalysis_block(domain["sub"], domain["coord"], "")
    assert not Assignment.objects.filter(submission=domain["sub"], status="ACTIVE").exists()


@pytest.mark.django_db
def test_restriction_release_does_not_reopen_other_ineligibility(domain):
    domain["sub"].workflow_status = "INELIGIBLE"
    domain["sub"].save(update_fields=["workflow_status"])
    with pytest.raises(ValidationError, match="pré-análise"):
        Eligibility.release_preanalysis_block(
            domain["sub"], domain["admin"], "Não é bloqueio cadastral"
        )
