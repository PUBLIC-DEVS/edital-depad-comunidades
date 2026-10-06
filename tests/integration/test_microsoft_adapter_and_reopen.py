"""Regressão: vínculo de conta do adaptador Microsoft e reabertura de análise.

Cobre o provisionamento institucional (ADR 0004) e a edição de registros antigos
pelo analista responsável, com os guardrails de workflow.
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.adapters.microsoft import MicrosoftAuthAdapter
from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy
from apps.evaluations.models import Evaluation
from apps.evaluations.services import EvaluationService
from apps.reviews.models import Review
from apps.reviews.services import ReviewService
from apps.submissions.models import Submission

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# Adaptador Microsoft / Entra ID                                              #
# --------------------------------------------------------------------------- #
def _claims(oid, email, upn=None):
    return {
        "oid": oid,
        "preferred_username": upn or email,
        "email": email,
        "given_name": "Nome",
        "family_name": "Sobrenome",
    }


def test_adapter_links_preprovisioned_account_preserving_role():
    """Conta criada pela administração (sem OID) é vinculada no 1º login, mantendo o papel."""
    pre = User.objects.create(
        username="daniel.brasileiro",
        email="daniel.brasileiro@mds.gov.br",
        role=User.Role.ADMINISTRADOR,
        is_staff=True,
        is_superuser=True,
    )
    pre.set_unusable_password()
    pre.save()

    adapter = MicrosoftAuthAdapter()
    user = adapter.authenticate_request(
        None, id_token="x", claims=_claims("oid-1", "daniel.brasileiro@mds.gov.br")
    )

    assert user is not None
    assert user.pk == pre.pk
    assert user.role == User.Role.ADMINISTRADOR
    assert user.is_superuser is True
    assert user.azure_oid == "oid-1"
    # segundo acesso encontra pelo OID e reutiliza a mesma conta
    again = adapter.authenticate_request(
        None, id_token="x", claims=_claims("oid-1", "daniel.brasileiro@mds.gov.br")
    )
    assert again.pk == pre.pk


def test_adapter_creates_new_user_with_least_privilege():
    adapter = MicrosoftAuthAdapter()
    user = adapter.authenticate_request(
        None, id_token="x", claims=_claims("oid-new", "novato@mds.gov.br")
    )
    assert user is not None
    assert user.role == User.Role.CONSULTA
    assert user.azure_oid == "oid-new"
    assert not user.has_usable_password()


def test_adapter_rejects_inactive_account():
    pre = User.objects.create(
        username="inativo", email="inativo@mds.gov.br", role=User.Role.CONSULTA, is_active=False
    )
    pre.azure_oid = "oid-inativo"
    pre.save()
    adapter = MicrosoftAuthAdapter()
    assert (
        adapter.authenticate_request(
            None, id_token="x", claims=_claims("oid-inativo", "inativo@mds.gov.br")
        )
        is None
    )


def test_adapter_without_token_or_claims_returns_none():
    adapter = MicrosoftAuthAdapter()
    assert adapter.authenticate_request(None) is None
    assert adapter.authenticate_request(None, id_token="x", claims={"oid": "só-oid"}) is None


# --------------------------------------------------------------------------- #
# Reabertura de análise concluída (editar registro antigo)                    #
# --------------------------------------------------------------------------- #
def _conclude(domain, status):
    ev = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    ev.check_results.update(status=status)
    return EvaluationService.conclude_evaluation(ev, domain["analyst"])


def test_analyst_can_reopen_own_pending_review_evaluation(domain):
    ev = _conclude(domain, "NAO_ATENDE")  # INAPTA -> PENDING_REVIEW + tarefa de revisão
    assert ev.status == Evaluation.Status.COMPLETED
    review_id = ev.review.id

    reopened = EvaluationService.reopen_evaluation(ev, domain["analyst"])

    assert reopened.status == Evaluation.Status.DRAFT
    assert reopened.completed_at is None
    domain["sub"].refresh_from_db()
    assert domain["sub"].workflow_status == Submission.WorkflowStatus.UNDER_ANALYSIS
    # a tarefa de revisão pendente e não atribuída é descartada
    assert not Review.objects.filter(pk=review_id).exists()


def test_reopen_blocked_when_review_already_claimed(domain):
    ev = _conclude(domain, "NAO_ATENDE")
    ReviewService.claim_review(ev.review, domain["reviewer"])

    with pytest.raises(ValidationError):
        EvaluationService.reopen_evaluation(ev, domain["analyst"])


def test_reopen_blocked_when_apta_and_eligible_for_ranking(domain):
    ev = _conclude(domain, "ATENDE")  # APTA -> ELIGIBLE_FOR_RANKING
    domain["sub"].refresh_from_db()
    assert domain["sub"].workflow_status == Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING

    with pytest.raises(ValidationError):
        EvaluationService.reopen_evaluation(ev, domain["analyst"])


def test_other_analyst_cannot_reopen(domain):
    ev = _conclude(domain, "NAO_ATENDE")
    assert RolePermissionPolicy.can_reopen_evaluation(domain["other_analyst"], ev) is False
    with pytest.raises(PermissionDenied):
        EvaluationService.reopen_evaluation(ev, domain["other_analyst"])
