"""Full operational 2026 lifecycle, built through Django screens without Excel."""

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Edital, RequirementCheck, RequirementValidationRule
from apps.evaluations.models import CheckResult, Evaluation
from apps.ranking.models import RankingSnapshot
from apps.reviews.models import Review
from apps.submissions.models import Assignment, ParticipationRestriction, Submission
from tests.phase17_helpers import configure_2026_through_http, post_ok


@pytest.mark.django_db
def test_edital_2026_operational_lifecycle_without_workbook(client):
    admin = User.objects.create_user(username="admin-2026", role=User.Role.ADMINISTRADOR)
    distributor = User.objects.create_user(username="distributor-2026", role=User.Role.DISTRIBUIDOR)
    analyst = User.objects.create_user(username="analyst-2026", role=User.Role.ANALISTA)
    reviewer = User.objects.create_user(username="reviewer-2026", role=User.Role.REVISOR)

    client.force_login(admin)
    edital, program, municipality = configure_2026_through_http(client)
    assert edital.requirements.filter(active=True).count() == 14
    assert RequirementCheck.objects.filter(requirement__edital=edital, active=True).count() == 23
    assert (
        RequirementValidationRule.objects.filter(
            requirement_check__requirement__edital=edital, active=True
        ).count()
        == 11
    )
    assert edital.requires_financial_rules is False

    # Preview is read-only and configuration is published only after validation.
    evaluation_count = Evaluation.objects.count()
    preview = client.get(reverse("edital-analyst-preview", args=[edital.pk]))
    assert preview.status_code == 200
    assert "nenhuma avaliação será criada" in preview.content.decode()
    assert Evaluation.objects.count() == evaluation_count
    post_ok(client, "edital-publish", [edital.pk])
    edital.refresh_from_db()
    assert edital.status == Edital.Status.ACTIVE
    assert edital.configuration_snapshots.count() == 1

    client.force_login(distributor)
    blocked_cnpj = "00000000000353"
    post_ok(
        client,
        "restriction-create",
        data={
            "edital": edital.pk,
            "cnpj": blocked_cnpj,
            "reason": "Contrato ativo informado pela fonte de teste",
            "source": "Cadastro manual de teste",
            "reference_period": "2024 e 2025",
            "active": "on",
        },
    )
    assert ParticipationRestriction.objects.filter(edital=edital, cnpj=blocked_cnpj).exists()

    def create_submission(sei, cnpj, name, *, female=0, male=0, mothers=0, minute=0):
        total = female + male + mothers
        post_ok(
            client,
            "submission-create",
            data={
                "edital": edital.pk,
                "processo_sei": sei,
                "received_at": f"2026-08-01T10:{minute:02d}",
                "institution_cnpj": cnpj,
                "institution_name": name,
                "institution_address": "Rua de teste, 10",
                "institution_postal_code": "01000-000",
                "municipality": municipality.pk,
                "vagas_femininas": female,
                "vagas_masculinas": male,
                "vagas_maes_nutrizes": mothers,
                "vagas_solicitadas": total,
                "capacidade_total": 20,
            },
        )
        return Submission.objects.get(edital=edital, processo_sei=sei)

    blocked = create_submission("2026-BLOCKED", blocked_cnpj, "OSC bloqueada", male=4)
    assert blocked.workflow_status == Submission.WorkflowStatus.INELIGIBLE
    assert not blocked.assignments.exists()
    assert not Evaluation.objects.filter(submission=blocked).exists()
    blocked_detail = client.get(reverse("submission-detail", args=[blocked.pk]))
    assert blocked_detail.status_code == 200
    assert "CONTRATO VIGENTE / PARTICIPAÇÃO BLOQUEADA" in blocked_detail.content.decode()
    assert "Atualizar Atribuição" not in blocked_detail.content.decode()

    apta_submission = create_submission(
        "2026-APTA", "00000000000191", "OSC feminina", female=4, minute=1
    )
    inapta_submission = create_submission(
        "2026-INAPTA", "11222333000181", "OSC masculina", male=4, minute=2
    )
    assert apta_submission.target_group == "G1"
    assert inapta_submission.target_group == "G2"
    assert apta_submission.institution.postal_code == "01000-000"

    duplicate = create_submission(
        "2026-DUPLICATE", "00000000000191", "OSC feminina", female=4, minute=3
    )
    assert duplicate.workflow_status == Submission.WorkflowStatus.RECEIVED
    assert not Evaluation.objects.filter(submission=duplicate).exists()
    client.get(reverse("submission-anomalies"), {"tipo": "DUPLICATE_CNPJ"})
    assert AuditEvent.objects.filter(
        entity_type="ParticipationRestriction", action="CREATE_RESTRICTION"
    ).exists()

    for submission in (apta_submission, inapta_submission):
        post_ok(
            client,
            "submission-assign",
            [submission.pk],
            {"analyst": analyst.pk, "reason": "Distribuição do Edital 2026"},
        )
        assert Assignment.objects.filter(
            submission=submission, status=Assignment.Status.ACTIVE, analyst=analyst
        ).exists()

    client.force_login(analyst)
    for submission, fail_one in ((apta_submission, False), (inapta_submission, True)):
        # Opening the workspace remains read-only until the assigned analyst posts Start.
        initial = Evaluation.objects.count()
        workspace = client.get(reverse("evaluation-workspace", args=[submission.pk]))
        assert workspace.status_code == 200
        assert Evaluation.objects.count() == initial
        post_ok(client, "evaluation-start", [submission.pk])
        evaluation = Evaluation.objects.get(submission=submission)
        payload = {}
        for result in evaluation.check_results.select_related("requirement_check", "requirement"):
            definition = result.definition
            status = "ATENDE"
            if definition.code == "COMPROVACAO_AUTODECLARADA":
                status = "NAO_ATENDE" if fail_one else "NAO_APLICAVEL"
            payload[f"{result.input_prefix}status"] = status
            for field in definition.evidence_fields:
                value = {
                    "sei_number": f"DOC-{result.pk}",
                    "pages": "1-2",
                    "document_cnpj": submission.institution.cnpj,
                    "valid_until": "2026-12-31",
                    "opened_on": "2020-01-01",
                    "cnae": "87.20-4-99",
                    "canonical_cnpj_confirmed": "on",
                    "notes": "Verificação operacional de teste.",
                }[field]
                payload[f"{result.input_prefix}{field}"] = value
        post_ok(client, "evaluation-save-draft", [evaluation.pk], payload)
        assert Evaluation.objects.get(pk=evaluation.pk).result == (
            Evaluation.Result.INAPTA if fail_one else Evaluation.Result.APTA
        )
        post_ok(client, "evaluation-conclude", [evaluation.pk])
        evaluation.refresh_from_db()
        submission.refresh_from_db()
        if fail_one:
            assert evaluation.result == Evaluation.Result.INAPTA
            assert submission.workflow_status == Submission.WorkflowStatus.PENDING_REVIEW
            review = Review.objects.get(evaluation=evaluation)
            assert review.reviewer is None
            client.force_login(reviewer)
            post_ok(client, "review-claim", [review.pk])
            failed_check = evaluation.check_results.get(status=CheckResult.Status.NAO_ATENDE)
            post_ok(
                client,
                "review-item-decision",
                [review.pk, failed_check.pk],
                {
                    "agrees_with_analyst": "false",
                    "reviewer_status": CheckResult.Status.ATENDE,
                    "justification": "Comprovante complementar conferido na revisão.",
                },
            )
            post_ok(
                client,
                "review-conclude",
                [review.pk],
                {
                    "preliminary_result": "PRE_HABILITADO",
                    "decision_notes": "Item impeditivo revisto e superado.",
                },
            )
            review.refresh_from_db()
            assert review.preliminary_result == "PRE_HABILITADO"
            submission.refresh_from_db()
            assert submission.workflow_status == Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
            client.force_login(analyst)
        else:
            assert evaluation.result == Evaluation.Result.APTA
            assert submission.workflow_status == Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
            assert not Review.objects.filter(evaluation=evaluation).exists()

    client.force_login(admin)
    post_ok(
        client,
        "ranking-generate-snapshot",
        data={
            "edital_id": edital.pk,
            "snapshot_type": "PRELIMINAR",
            "description": "Classificação operacional configurada sem planilha",
        },
    )
    snapshot = RankingSnapshot.objects.get(edital=edital)
    assert list(snapshot.entries.order_by("target_group").values_list("position", flat=True)) == [
        1,
        1,
    ]
    assert set(snapshot.entries.values_list("submission_id", flat=True)) == {
        apta_submission.pk,
        inapta_submission.pk,
    }
    metrics = client.get(reverse("reporting:dashboard"), {"edital": edital.pk})
    assert metrics.status_code == 200
    assert metrics.context["summary"]["initial_results"] == {
        "APTA": 1,
        "INAPTA": 1,
        "EM_ANALISE": 0,
    }
    consolidated = metrics.context["summary"]["consolidated_results"]
    assert consolidated["CLASSIFICADO"] == 2
    assert consolidated["INABILITADO"] == 1
    assert consolidated["RECEBIDO"] == 1
    assert sum(consolidated.values()) == 4
    assert (
        AuditEvent.objects.filter(
            entity_type="CheckResult", action="FIELD_CHANGE", field="status"
        ).count()
        == 46
    )
