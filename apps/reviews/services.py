"""Auditable reviewer decisions over an immutable original evaluation."""

import json

from django.core.exceptions import PermissionDenied, ValidationError
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
    def claim_review(cls, review, actor):
        from apps.accounts.permissions import RolePermissionPolicy

        if not RolePermissionPolicy.can_conduct_review(actor):
            raise PermissionDenied("Sem permissão de revisão.")
        locked = Review.objects.select_for_update().select_related("evaluation").get(pk=review.pk)
        if locked.evaluation.analyst_id == actor.pk:
            raise PermissionDenied("Analista não pode revisar sua própria análise.")
        if locked.status != Review.Status.PENDING or locked.reviewer_id is not None:
            raise ValidationError("Revisão já assumida ou concluída.")
        claimed = Review.objects.filter(
            pk=locked.pk, reviewer__isnull=True, status=Review.Status.PENDING
        ).update(reviewer=actor)
        if claimed != 1:
            raise ValidationError("Outro revisor assumiu a revisão.")
        locked.reviewer = actor
        AuditEvent.objects.create(
            actor=actor, entity_type="Review", entity_id=str(locked.pk), action="CLAIM_REVIEW"
        )
        return locked

    @staticmethod
    def enforce_edit(review, actor):
        from apps.accounts.permissions import RolePermissionPolicy

        if actor is None or not RolePermissionPolicy.can_edit_review(actor, review):
            raise PermissionDenied("Revisão exige responsável atribuído e estado pendente.")

    @classmethod
    @transaction.atomic
    def record_effective_status(cls, review, check_result_id, status, justification, actor):
        check = (
            CheckResult.objects.select_related("requirement", "requirement_check")
            .filter(pk=check_result_id, evaluation_id=review.evaluation_id)
            .first()
        )
        if check is None:
            raise ValidationError("Checagem não pertence à avaliação desta revisão.")
        if status not in {"ATENDE", "NAO_ATENDE", "NAO_APLICAVEL"}:
            raise ValidationError("Escolha Atende, Não atende ou Não se aplica quando permitido.")
        return cls.record_item_decision(
            review, check_result_id, status == check.status, status, justification, actor
        )

    @staticmethod
    def effective_assessment(review, rows=None):
        from apps.evaluations.services import EvaluationService

        overrides = {
            d.check_result_id: d.reviewer_status
            for d in review.item_decisions.all()
            if not d.agrees_with_analyst
        }
        return EvaluationService.calculate_assessment(review.evaluation, overrides, rows=rows)

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
        review = Review.objects.select_for_update().get(pk=review.pk)
        cls.enforce_edit(review, actor)
        if not agrees_with_analyst and reviewer_status not in CheckResult.Status.values:
            raise ValidationError("Status do revisor inválido.")
        if not agrees_with_analyst and not justification.strip():
            msg = "Justificativa obrigatória em caso de discordância do parecer do analista."
            raise ValidationError(msg)

        check_result = CheckResult.objects.filter(
            id=check_result_id, evaluation_id=review.evaluation_id
        ).first()
        if check_result is None:
            raise ValidationError("Checagem não pertence à avaliação desta revisão.")
        if (
            not agrees_with_analyst
            and reviewer_status not in check_result.definition.allowed_statuses
        ):
            raise ValidationError("Status não permitido para este item.")

        previous = (
            ReviewItemDecision.objects.filter(review=review, check_result=check_result)
            .values("agrees_with_analyst", "reviewer_status", "justification")
            .first()
        )
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
            field="effective_decision",
            old_value="" if created else json.dumps(previous, ensure_ascii=False),
            new_value=json.dumps(
                {
                    "agrees_with_analyst": agrees_with_analyst,
                    "reviewer_status": decision.reviewer_status,
                    "justification": justification,
                },
                ensure_ascii=False,
            ),
            metadata={
                "review_id": review.id,
                "check_code": check_result.definition.code,
                "original_status": check_result.status,
                "effective_status": check_result.status if agrees_with_analyst else reviewer_status,
            },
        )
        return decision

    @classmethod
    @transaction.atomic
    def conclude_review(
        cls,
        review: Review,
        preliminary_result: str | None = None,
        decision_notes: str = "",
        actor: User | None = None,
    ) -> Review:
        """Conclui a revisão e avança o workflow da submissão para elegibilidade ou inaptidão.

        - PRE_HABILITADO -> ELIGIBLE_FOR_RANKING
        - PRE_INABILITADO -> INELIGIBLE
        """
        review = Review.objects.select_for_update().select_related("submission").get(pk=review.pk)
        cls.enforce_edit(review, actor)
        if preliminary_result is not None and preliminary_result not in (
            Review.PreliminaryResult.PRE_HABILITADO,
            Review.PreliminaryResult.PRE_INABILITADO,
        ):
            raise ValidationError("Resultado preliminar inválido para conclusão.")
        from apps.evaluations.services import EvaluationService

        blocking = EvaluationService.blocking_check_results(review.evaluation)
        decisions = {d.check_result_id: d for d in review.item_decisions.all()}
        missing = [cr.definition.code for cr in blocking if cr.pk not in decisions]
        if missing:
            raise ValidationError(
                f"Trate todos os itens impeditivos antes de concluir: {', '.join(missing)}."
            )
        overrides = {
            pk: decision.reviewer_status
            for pk, decision in decisions.items()
            if not decision.agrees_with_analyst
        }
        assessment = EvaluationService.calculate_assessment(review.evaluation, overrides)
        calculated_result = (
            Review.PreliminaryResult.PRE_HABILITADO
            if assessment.result == "APTA"
            else Review.PreliminaryResult.PRE_INABILITADO
        )
        if not assessment.is_complete or (
            preliminary_result is not None and preliminary_result != calculated_result
        ):
            raise ValidationError(
                "Resultado da revisão incoerente com as decisões dos itens. Corrija as decisões antes de concluir."
            )
        preliminary_result = calculated_result
        review.status = Review.Status.COMPLETED
        review.preliminary_result = preliminary_result
        review.decision_notes = decision_notes
        review.completed_at = timezone.now()
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
