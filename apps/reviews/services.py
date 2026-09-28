"""Serviços de domínio para o fluxo de revisão e diligências processuais."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.evaluations.models import CheckResult
from apps.reviews.models import Review, ReviewItemDecision
from apps.submissions.models import Submission
from apps.submissions.services.workflow import WorkflowService


class ReviewServiceError(Exception):
    """Exceção base para erros na camada de revisão."""


class ReviewService:
    """Orquestrador do ciclo de vida das revisões e decisões item a item."""

    @classmethod
    @transaction.atomic
    def record_item_decision(
        cls,
        review: Review,
        check_result_id: int,
        agrees_with_analyst: bool,
        reviewer_status: str = "",
        justification: str = "",
        actor: User | None = None,
    ) -> ReviewItemDecision:
        """Registra a manifestação do revisor sobre uma checagem específica.

        Regra de Integridade: Em caso de discordância (divergência),
        a justificativa técnica fundamentada é obrigatória.
        """
        if not agrees_with_analyst and not justification.strip():
            msg = "Justificativa obrigatória em caso de discordância do parecer do analista."
            raise ValidationError(msg)

        check_result = CheckResult.objects.get(id=check_result_id)

        decision, created = ReviewItemDecision.objects.update_or_create(
            review=review,
            check_result=check_result,
            defaults={
                "agrees_with_analyst": agrees_with_analyst,
                "reviewer_status": reviewer_status if not agrees_with_analyst else "",
                "justification": justification,
            },
        )

        AuditEvent.objects.create(
            actor=actor or review.reviewer,
            entity_type="ReviewItemDecision",
            entity_id=str(decision.id),
            action="RECORD_DECISION",
            field="agrees_with_analyst",
            old_value="" if created else "UPDATED",
            new_value="CONCORDA" if agrees_with_analyst else f"DIVERGE ({reviewer_status})",
            metadata={
                "review_id": review.id,
                "check_code": check_result.requirement_check.code,
                "justification": justification[:100],
            },
        )
        return decision

    @classmethod
    @transaction.atomic
    def conclude_review(
        cls,
        review: Review,
        preliminary_result: str,
        decision_notes: str,
        actor: User,
    ) -> Review:
        """Conclui a revisão e avança o workflow da submissão para elegibilidade ou inaptidão.

        - PRE_HABILITADO -> ELIGIBLE_FOR_RANKING
        - PRE_INABILITADO -> INELIGIBLE
        """
        review.status = Review.Status.COMPLETED
        review.preliminary_result = preliminary_result
        review.decision_notes = decision_notes
        review.completed_at = timezone.now()
        review.reviewer = actor
        review.save()

        submission = review.submission
        if preliminary_result == Review.PreliminaryResult.PRE_HABILITADO:
            target_status = Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
            reason = f"Revisão concluída: Pré-Habilitado por {actor.username}."
        else:
            target_status = Submission.WorkflowStatus.INELIGIBLE
            reason = f"Revisão concluída: Pré-Inabilitado por {actor.username}."

        WorkflowService.transition(
            submission=submission,
            target_status=target_status,
            actor=actor,
            reason=reason,
            metadata={"review_id": review.id, "preliminary_result": preliminary_result},
        )

        AuditEvent.objects.create(
            actor=actor,
            entity_type="Review",
            entity_id=str(review.id),
            action="CONCLUDE_REVIEW",
            new_value=preliminary_result,
            metadata={"decision_notes": decision_notes[:200]},
        )
        return review
