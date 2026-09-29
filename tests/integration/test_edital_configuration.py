from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.editais.models import (
    ClassificationPolicy,
    Edital,
    FundingRule,
    Program,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
    TargetGroup,
)
from apps.editais.services import EditalConfigurationService
from apps.evaluations.services import EvaluationService
from apps.ranking.services import ClassificationService
from apps.submissions.models import Submission


@pytest.fixture
def configured(domain):
    edital = domain["edital"]
    edital.target_groups.all().delete()
    edital.classification_policy.delete()
    edital.closes_at += timedelta(days=30)
    edital.save()
    TargetGroup.objects.create(
        edital=edital, code="G4", name="Quarto público", order=1, vacancy_types=["MALE"]
    )
    ClassificationPolicy.objects.create(edital=edital)
    FundingRule.objects.create(
        edital=edital, vacancy_type="MALE", monthly_value=Decimal("900.00"), duration_months=8
    )
    return domain


@pytest.mark.django_db
def test_publication_freezes_rules_and_captures_version(configured, client):
    d = configured
    client.force_login(d["admin"])
    response = client.post(reverse("edital-publish", args=[d["edital"].pk]))
    assert response.status_code == 302
    edital = Edital.objects.get(pk=d["edital"].pk)
    assert edital.status == "ACTIVE"
    snapshot = edital.configuration_snapshots.get()
    assert snapshot.configuration["groups"][0]["code"] == "G4"
    # The pre-publication object is deliberately stale: ORM protection re-reads the DB.
    d["check"].name = "Silently changed rule"
    with pytest.raises(ValidationError):
        d["check"].save()
    with pytest.raises(ValidationError):
        Requirement.objects.filter(edital=edital).update(name="Changed")
    with pytest.raises(ValidationError):
        Edital.objects.filter(pk=edital.pk).update(rules_version="2")
    with pytest.raises(PermissionDenied):
        snapshot.configuration = {}
        snapshot.save()
    with pytest.raises(PermissionDenied):
        type(snapshot).objects.all().delete()
    with pytest.raises(ValidationError):
        TargetGroup.objects.create(edital=edital, code="NEW", name="New")
    assert client.get(reverse("edital-edit", args=[edital.pk])).status_code == 403


@pytest.mark.django_db
def test_validation_reports_missing_sections(domain, client):
    d = domain
    d["edital"].target_groups.all().delete()
    validation = EditalConfigurationService.validate(d["edital"])
    assert not validation["can_publish"]
    assert any("grupo" in error for error in validation["errors"])
    client.force_login(d["admin"])
    response = client.post(reverse("edital-publish", args=[d["edital"].pk]), follow=True)
    assert response.status_code == 200
    assert not d["edital"].configuration_snapshots.exists()
    assert "Edital ainda não pode" in response.content.decode()


@pytest.mark.django_db
def test_clone_configuration_only(configured, client):
    d = configured
    EditalConfigurationService.publish(d["edital"], d["admin"])
    client.force_login(d["admin"])
    response = client.post(
        reverse("edital-clone", args=[d["edital"].pk]),
        {
            "name": "Edição nova",
            "number": "next",
            "year": 2027,
            "rules_version": "2.0",
            "opens_at": "2027-01-01T08:00",
            "closes_at": "2027-02-01T08:00",
        },
    )
    assert response.status_code == 302
    clone = Edital.objects.get(number="next", year=2027)
    assert clone.status == "DRAFT" and clone.published_at is None
    assert clone.cloned_from_id == d["edital"].pk
    assert clone.requirements.get().checks.count() == 1
    assert clone.target_groups.get().code == "G4"
    assert clone.funding_rules.get().monthly_value == Decimal("900.00")
    assert clone.classification_policy.policy_type == "VACANCY_TARGET_POLICY_V1"
    assert clone.submissions.count() == clone.configuration_snapshots.count() == 0
    events = AuditEvent.objects.filter(entity_type="Edital", entity_id=str(clone.pk))
    assert list(events.values_list("action", flat=True)) == ["CLONE_CONFIGURATION"]


@pytest.mark.django_db
def test_configurable_group_and_program_classification(configured):
    d = configured
    program = Program.objects.create(code="TERRITORIO", name="Territórios prioritários")
    group = d["edital"].target_groups.get()
    group.program = program
    group.save()
    assert ClassificationService.classify_submission(d["sub"]) == "SEM_GRUPO"
    ProgramMunicipality.objects.create(
        edital=d["edital"],
        program=program,
        program_name=program.code,
        municipality=d["sub"].municipality,
    )
    ClassificationService.classify_and_update(d["sub"], d["admin"])
    d["sub"].refresh_from_db()
    assert d["sub"].target_group == "G4"
    assert d["sub"].target_group_definition_id == group.pk


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["analyst", "reviewer", "consulta", "distributor"])
def test_structural_configuration_denies_other_roles(domain, client, role):
    client.force_login(domain[role])
    assert client.get(reverse("edital-list")).status_code == 403
    assert client.post(reverse("edital-publish", args=[domain["edital"].pk])).status_code == 403
    assert client.get(reverse("catalog-create", args=["usuarios"])).status_code == 403


@pytest.mark.django_db
def test_coordinator_configuration_is_read_only(configured, client):
    client.force_login(configured["coord"])
    assert client.get(reverse("edital-detail", args=[configured["edital"].pk])).status_code == 200
    assert client.get(reverse("edital-create")).status_code == 403
    assert client.post(reverse("edital-publish", args=[configured["edital"].pk])).status_code == 403


@pytest.mark.django_db
def test_check_parent_is_scoped_to_edital(configured, client):
    client.force_login(configured["admin"])
    other = Edital.objects.create(
        name="Outro",
        number="other",
        year=2027,
        opens_at=timezone.now(),
        closes_at=timezone.now() + timedelta(days=30),
    )
    req = Requirement.objects.create(edital=other, code="OTHER", name="Outro requisito")
    response = client.post(
        reverse("edital-section-create", args=[configured["edital"].pk, "subcriterios"]),
        {
            "requirement": req.pk,
            "code": "BAD",
            "name": "Ataque",
            "order": 1,
            "allowed_statuses": ["ATENDE"],
        },
    )
    assert response.status_code == 200
    assert not RequirementCheck.objects.filter(code="BAD").exists()


@pytest.mark.django_db
def test_csv_intake_is_transactional_and_excel_independent(configured, client):
    d = configured
    EditalConfigurationService.publish(d["edital"], d["admin"])
    client.force_login(d["distributor"])
    header = "processo_sei,recebido_em,cnpj,instituicao,ibge,vagas_femininas,vagas_masculinas,vagas_maes_nutrizes,vagas_solicitadas,capacidade_total,contato_email"
    stamp = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
    valid = f"CSV-1,{stamp},11222333000181,Entidade CSV,3550308,0,5,0,5,10,contato@csv.example"
    invalid = f"CSV-2,{stamp},00000000000353,Outra entidade,9999999,0,4,0,4,10,"

    def upload(body):
        return client.post(
            reverse("submission-import-csv"),
            {
                "edital": d["edital"].pk,
                "file": SimpleUploadedFile("processos.csv", body.encode(), content_type="text/csv"),
            },
        )

    assert upload("\n".join([header, valid, invalid])).status_code == 200
    assert not Submission.objects.filter(
        edital=d["edital"], processo_sei__startswith="CSV-"
    ).exists()
    assert AuditEvent.objects.filter(action="CREATE_CSV").count() == 0
    assert (
        upload("\n".join([header, valid, invalid.replace("9999999", "3550308")])).status_code == 302
    )
    imported = list(
        Submission.objects.filter(edital=d["edital"], processo_sei__startswith="CSV-").order_by(
            "processo_sei"
        )
    )
    assert len(imported) == 2
    assert [sub.target_group for sub in imported] == ["G4", "G4"]
    assert imported[0].valor_global == Decimal("36000.00")
    assert imported[0].institution.contact_email == "contato@csv.example"
    assert AuditEvent.objects.filter(action="CREATE_CSV", entity_type="Submission").count() == 2
    client.force_login(d["analyst"])
    assert client.post(reverse("submission-import-csv")).status_code == 403


@pytest.mark.django_db
def test_requirement_check_crud_and_direct_requirement(configured, client):
    d = configured
    client.force_login(d["admin"])
    edital = d["edital"]
    response = client.post(
        reverse("edital-section-create", args=[edital.pk, "requisitos"]),
        {
            "code": "DIRETO",
            "name": "Termo direto",
            "order": 2,
            "mandatory": "on",
            "active": "on",
            "failure_behavior": "NONE",
            "allowed_statuses": ["ATENDE", "NAO_APLICAVEL"],
            "accepted_statuses": ["ATENDE", "NAO_APLICAVEL"],
            "collect_numeric_value": "on",
        },
    )
    assert response.status_code == 302
    direct = edital.requirements.get(code="DIRETO")
    assert direct.checks.count() == 0
    assert direct.collect_numeric_value and not direct.collect_pages
    check = d["check"]
    response = client.post(
        reverse("edital-section-edit", args=[edital.pk, "subcriterios", check.pk]),
        {
            "requirement": check.requirement_id,
            "code": check.code,
            "name": check.name,
            "order": 3,
            "active": "on",
            "contributes_to_result": "on",
            "allowed_statuses": ["ATENDE", "NAO_ATENDE"],
            "accepted_statuses": ["ATENDE"],
            "failure_statuses": ["NAO_ATENDE"],
            "collect_document_cnpj": "on",
            "collect_valid_until": "on",
        },
    )
    assert response.status_code == 302
    check.refresh_from_db()
    assert check.allowed_statuses == ["ATENDE", "NAO_ATENDE"]
    assert check.collect_document_cnpj and check.collect_valid_until
    assert not check.required and not check.collect_sei_number
    response = client.post(
        reverse("edital-section-action", args=[edital.pk, "requisitos", direct.pk, "up"])
    )
    assert response.status_code == 302
    direct.refresh_from_db()
    assert direct.order == 1
    response = client.post(
        reverse("edital-section-action", args=[edital.pk, "subcriterios", check.pk, "desativar"])
    )
    assert response.status_code == 302
    check.refresh_from_db()
    assert not check.active
    evaluation = EvaluationService.start_evaluation(d["sub"], d["analyst"])
    assert evaluation.check_results.filter(requirement_check__isnull=True).count() == 2
