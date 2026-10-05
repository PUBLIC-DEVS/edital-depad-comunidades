"""Product acceptance: configure and execute a different edital through HTTP, without Excel."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Edital, Program
from apps.evaluations.models import Evaluation
from apps.institutions.models import Municipality
from apps.ranking.models import RankingSnapshot
from apps.reviews.models import Diligence, Review
from apps.submissions.models import Submission

# Test-only routes exercise retained configuration; operational retirement has separate coverage.
pytestmark = pytest.mark.urls("tests.technical_urls")


@pytest.mark.django_db
def test_new_edital_full_lifecycle(client):
    admin = User.objects.create_user(username="bootstrap-admin", role="ADMINISTRADOR")
    client.force_login(admin)

    def post(name, args=(), data=None):
        response = client.post(reverse(name, args=args), data or {})
        assert response.status_code == 302, response.content.decode()
        return response

    # The only pre-existing account is the bootstrap administrator.
    for role in ("ANALISTA", "REVISOR", "DISTRIBUIDOR", "CONSULTA"):
        post(
            "catalog-create",
            ["usuarios"],
            {
                "username": role.lower(),
                "email": f"{role.lower()}@product.example",
                "role": role,
                "is_active": "on",
                "new_password": "Different.Product#2027",
            },
        )
    post(
        "edital-create",
        data={
            "name": "Edital operacional novo",
            "number": "27",
            "year": 2027,
            "description": "Configurado sem arquivo externo",
            "opens_at": "2027-01-01T08:00",
            "closes_at": "2027-03-01T18:00",
            "rules_version": "1.0",
            "minimum_equity_percentage": "15.00",
            "requires_financial_rules": "on",
            "duplicate_policy": "KEEP_EARLIEST_SUBMISSION",
            "duplicate_scope": "ELIGIBLE",
            "tie_breaker_policy": "UNRESOLVED",
        },
    )
    edital = Edital.objects.get(number="27")
    post(
        "catalog-create",
        ["municipios"],
        {"ibge_code": "3106200", "name": "Belo Horizonte", "state": "MG"},
    )
    municipality = Municipality.objects.get(ibge_code="3106200")
    post(
        "program-create",
        data={"code": "TERRITORIOS", "name": "Territórios prioritários", "active": "on"},
    )
    program = Program.objects.get(code="TERRITORIOS")
    post(
        "edital-section-create",
        [edital.pk, "programas"],
        {"program": program.pk, "municipality": municipality.pk, "active": "on"},
    )
    for order, code, types, program_id in [
        (1, "NUTRIZES", ["NURSING_MOTHER"], ""),
        (2, "FEMININO", ["FEMALE"], ""),
        (3, "PRIORITARIO", ["MALE"], program.pk),
        (4, "GERAL", ["MALE"], ""),
    ]:
        post(
            "edital-section-create",
            [edital.pk, "grupos"],
            {
                "code": code,
                "name": code.title(),
                "order": order,
                "active": "on",
                "vacancy_types": types,
                "program": program_id,
            },
        )
    assert edital.target_groups.count() == 4
    post(
        "edital-section-create",
        [edital.pk, "classificacao"],
        {"policy_type": "VACANCY_TARGET_POLICY_V1"},
    )
    for vacancy_type, value in [
        ("FEMALE", "800.00"),
        ("MALE", "900.00"),
        ("NURSING_MOTHER", "1300.00"),
    ]:
        post(
            "edital-section-create",
            [edital.pk, "financeiro"],
            {
                "vacancy_type": vacancy_type,
                "monthly_value": value,
                "duration_months": 6,
                "valid_from": "2027-01-01",
                "valid_until": "2027-12-31",
            },
        )
    statuses = {
        "allowed_statuses": ["ATENDE", "NAO_ATENDE"],
        "accepted_statuses": ["ATENDE"],
        "failure_statuses": ["NAO_ATENDE"],
    }
    for code, order in [("DOCUMENTACAO", 1), ("INSCRICAO", 2)]:
        post(
            "edital-section-create",
            [edital.pk, "requisitos"],
            {
                "code": code,
                "name": code.title(),
                "order": order,
                "mandatory": "on",
                "active": "on",
                "failure_behavior": "SEND_TO_REVIEW",
                "collect_sei_number": "on",
                "collect_pages": "on",
                **statuses,
            },
        )
    req = edital.requirements.get(code="DOCUMENTACAO")
    post(
        "edital-section-create",
        [edital.pk, "subcriterios"],
        {
            "requirement": req.pk,
            "code": "ASSINATURA",
            "name": "Assinatura responsável",
            "order": 1,
            "required": "on",
            "active": "on",
            "contributes_to_result": "on",
            "collect_sei_number": "on",
            "collect_pages": "on",
            **statuses,
        },
    )
    post("edital-publish", [edital.pk])
    edital.refresh_from_db()
    assert edital.status == "ACTIVE" and edital.published_by == admin
    assert edital.configuration_snapshots.count() == 1

    distributor = User.objects.get(username="distribuidor")
    analyst = User.objects.get(username="analista")
    client.force_login(distributor)
    for index, cnpj in enumerate(["00000000000191", "11222333000181"], 1):
        post(
            "submission-create",
            data={
                "edital": edital.pk,
                "processo_sei": f"NOVO-{index}",
                "received_at": f"2027-01-10T09:0{index}",
                "institution_cnpj": cnpj,
                "institution_name": f"Instituição nova {index}",
                "municipality": municipality.pk,
                "vagas_femininas": 0,
                "vagas_masculinas": 5,
                "vagas_maes_nutrizes": 0,
                "vagas_solicitadas": 5,
                "capacidade_total": 10,
            },
        )
    subs = list(Submission.objects.filter(edital=edital).order_by("processo_sei"))
    for sub in subs:
        assert sub.target_group == "PRIORITARIO"
        assert sub.valor_global == Decimal("27000.00")
        assert sub.patrimonio_minimo == Decimal("4050.00")
        post(
            "submission-assign", [sub.pk], {"analyst": analyst.pk, "reason": "Distribuição inicial"}
        )

    client.force_login(analyst)
    for index, sub in enumerate(subs, 1):
        assert client.get(reverse("evaluation-workspace", args=[sub.pk])).status_code == 200
        assert not Evaluation.objects.filter(submission=sub).exists()
        post("evaluation-start", [sub.pk])
        evaluation = Evaluation.objects.get(submission=sub)
        assert evaluation.configuration_snapshot_id == edital.configuration_snapshots.get().pk
        results = list(evaluation.check_results.all())
        assert len(results) == 2  # One check and one requirement evaluated directly.
        page = client.get(reverse("evaluation-workspace", args=[sub.pk])).content.decode()
        assert "document_cnpj" not in page and "numeric_value" not in page
        payload = {}
        for cr in results:
            payload[f"{cr.input_prefix}status"] = (
                "NAO_ATENDE" if index == 2 and cr.requirement_check_id else "ATENDE"
            )
            payload[f"{cr.input_prefix}sei_number"] = f"DOC-{index}"
            payload[f"{cr.input_prefix}pages"] = "1"
        post("evaluation-save-draft", [evaluation.pk], payload)
        post("evaluation-conclude", [evaluation.pk])
    subs[0].refresh_from_db()
    assert subs[0].workflow_status == "ELIGIBLE_FOR_RANKING"
    assert not Review.objects.filter(submission=subs[0]).exists()
    review = Review.objects.get(submission=subs[1])
    reviewer = User.objects.get(username="revisor")
    client.force_login(reviewer)
    post("review-claim", [review.pk])
    post(
        "review-conclude",
        [review.pk],
        {"preliminary_result": "PRE_HABILITADO", "decision_notes": "Tentativa incompleta"},
    )
    review.refresh_from_db()
    assert review.status == "PENDING"
    # EXPECTED_PRODUCT_CHANGE: no documentary clarification subflow can be started.
    assert client.post(reverse("diligence-create", args=[subs[1].pk])).status_code == 404
    assert not Diligence.objects.exists()
    failed = review.evaluation.check_results.get(status="NAO_ATENDE")
    post(
        "review-item-decision",
        [review.pk, failed.pk],
        {
            "agrees_with_analyst": "false",
            "reviewer_status": "ATENDE",
            "justification": "Assinatura conferida na revisão",
        },
    )
    post(
        "review-conclude",
        [review.pk],
        {"preliminary_result": "PRE_HABILITADO", "decision_notes": "Impedimento resolvido"},
    )
    review.refresh_from_db()
    assert review.status == "COMPLETED"

    client.force_login(admin)
    post(
        "ranking-generate-snapshot",
        data={
            "edital_id": edital.pk,
            "snapshot_type": "PRELIMINAR",
            "description": "Primeiro ranking operacional",
        },
    )
    snapshot = RankingSnapshot.objects.get(edital=edital)
    assert list(snapshot.entries.values_list("position", flat=True)) == [1, 2]
    assert set(snapshot.entries.values_list("target_group", flat=True)) == {"PRIORITARIO"}
    response = client.get(reverse("reporting:dashboard"), {"edital": edital.pk})
    assert response.status_code == 200
    summary = response.context["summary"]
    assert summary["apt_count"] == 2
    assert summary["inapt_count"] == 0
    assert summary["total_received"] == 2
    assert (
        AuditEvent.objects.filter(
            entity_type="CheckResult", action="FIELD_CHANGE", field="status"
        ).count()
        == 4
    )
    assert client.get(reverse("reporting:export-csv"), {"edital": edital.pk}).status_code == 200
    client.force_login(User.objects.get(username="consulta"))
    assert client.get(reverse("ranking-index")).status_code == 200
    assert client.post(reverse("edital-publish", args=[edital.pk])).status_code == 403
