import pytest

from apps.editais.edital_2026 import configure_edital_2026_base
from apps.editais.models import Edital
from apps.evaluations.models import CheckResult
from apps.evaluations.services import EvaluationService, InconsistentEvaluationError


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status, expected",
    [
        ("ATENDE", "APTA"),
        ("NAO_ATENDE", "INAPTA"),
        ("NAO_APLICAVEL", "APTA"),
        ("EM_BRANCO", "EM_ANALISE"),
    ],
)
def test_anexo_iii_autodeclarada_required_when_applicable(domain, status, expected):
    edital = Edital.objects.create(
        name="2026",
        number="proof",
        year=2026,
        opens_at=domain["edital"].opens_at,
        closes_at=domain["edital"].closes_at,
    )
    configure_edital_2026_base(edital, domain["admin"])
    domain["sub"].edital = edital
    domain["sub"].save(update_fields=["edital"])
    evaluation = EvaluationService.initialize_evaluation(domain["sub"], domain["analyst"])
    payloads = [
        {"check_result_id": item.pk, "status": "ATENDE"} for item in evaluation.check_results.all()
    ]
    proof = evaluation.check_results.get(requirement_check__code="COMPROVACAO_AUTODECLARADA")
    for payload in payloads:
        if payload["check_result_id"] == proof.pk:
            payload["status"] = status
    assessment = EvaluationService.save_draft(evaluation, payloads, domain["analyst"])
    assert assessment.result == expected
    if status == "NAO_ATENDE":
        assert "ANEXO_III" in assessment.failed_requirement_codes
        assert proof.pk in [
            item.pk for item in EvaluationService.blocking_check_results(evaluation)
        ]
    if status == CheckResult.Status.EM_BRANCO:
        assert assessment.pending_checks == 1
        with pytest.raises(InconsistentEvaluationError, match="pendentes"):
            EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
