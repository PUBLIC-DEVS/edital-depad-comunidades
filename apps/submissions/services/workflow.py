"""Máquina de estados finita e serviço de workflow de inscrições de editais."""

import datetime
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.evaluations.models import Evaluation
from apps.reviews.models import Diligence, Review
from apps.submissions.models import Assignment, Submission


class WorkflowError(Exception):
    """Exceção base de erros de workflow."""


class InvalidWorkflowTransitionError(WorkflowError):
    """Lançada quando se tenta executar uma transição de estado proibida."""


class WorkflowService:
    """Orquestrador do ciclo de vida e transições de estado das inscrições."""

    # Matriz explícita de transições permitidas
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        Submission.WorkflowStatus.RECEIVED: {
            Submission.WorkflowStatus.ASSIGNED,
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.ASSIGNED: {
            Submission.WorkflowStatus.UNDER_ANALYSIS,
            Submission.WorkflowStatus.PENDING_REVIEW,
            Submission.WorkflowStatus.ASSIGNED,  # Redistribuição
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.UNDER_ANALYSIS: {
            Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
            Submission.WorkflowStatus.PENDING_REVIEW,
            Submission.WorkflowStatus.PENDING_DILIGENCE,
            Submission.WorkflowStatus.INELIGIBLE,
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.PENDING_REVIEW: {
            Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
            Submission.WorkflowStatus.INELIGIBLE,
            Submission.WorkflowStatus.PENDING_DILIGENCE,
            Submission.WorkflowStatus.UNDER_ANALYSIS,  # Retorno para complementação
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.PENDING_DILIGENCE: {
            Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
            Submission.WorkflowStatus.UNDER_ANALYSIS,
            Submission.WorkflowStatus.PENDING_REVIEW,
            Submission.WorkflowStatus.INELIGIBLE,
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING: {
            Submission.WorkflowStatus.RANKED,
            Submission.WorkflowStatus.INELIGIBLE,
            Submission.WorkflowStatus.PENDING_DILIGENCE,
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.RANKED: {
            Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,  # Reclassificação / novo snapshot
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.INELIGIBLE: {
            Submission.WorkflowStatus.PENDING_DILIGENCE,  # Fase recursal / esclarecimento
            Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,  # Provimento de recurso
            Submission.WorkflowStatus.CLOSED,
        },
        Submission.WorkflowStatus.CLOSED: {
            Submission.WorkflowStatus.RECEIVED,  # Reabertura excepcional
        },
    }

    @classmethod
    @transaction.atomic
    def transition(
        cls,
        submission: Submission,
        target_status: str,
        actor: User,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Submission:
        """Executa a transição de estado da submissão com validação estrita e auditoria."""
        current_status = submission.workflow_status
        locked = Submission.objects.select_for_update().get(pk=submission.pk)
        current_status = locked.workflow_status
        if actor is not None and actor.role == User.Role.CONSULTA and not actor.is_superuser:
            raise PermissionDenied("Consulta não pode alterar workflow.")
        allowed = cls.ALLOWED_TRANSITIONS.get(current_status, set())

        if target_status not in allowed:
            msg = (
                f"Transição inválida de '{current_status}' para '{target_status}' "
                f"no processo {submission.processo_sei}."
            )
            raise InvalidWorkflowTransitionError(msg)

        submission.workflow_status = target_status
        submission.save(update_fields=["workflow_status", "updated_at"])

        event_metadata = metadata.copy() if metadata else {}
        if reason:
            event_metadata["reason"] = reason

        AuditEvent.objects.create(
            actor=actor,
            entity_type="Submission",
            entity_id=str(submission.id),
            action="WORKFLOW_TRANSITION",
            field="workflow_status",
            old_value=current_status,
            new_value=target_status,
            metadata=event_metadata,
        )

        return submission

    @classmethod
    @transaction.atomic
    def assign_analyst(
        cls,
        submission: Submission,
        analyst: User,
        assigned_by: User,
        reason: str = "",
    ) -> Assignment:
        """Atribui ou redistribui a submissão a um analista."""
        now = timezone.now()
        Submission.objects.select_for_update().get(pk=submission.pk)
        if not (
            assigned_by.is_superuser
            or assigned_by.role
            in {User.Role.ADMINISTRADOR, User.Role.COORDENADOR, User.Role.DISTRIBUIDOR}
        ):
            raise PermissionDenied("Sem permissão de distribuição.")
        if analyst.role != User.Role.ANALISTA:
            raise ValidationError("Responsável deve ser analista.")
        if Evaluation.objects.filter(submission=submission).exists():
            raise ValidationError(
                "Redistribuição bloqueada após início da avaliação; transferência formal necessária."
            )

        # Encerra atribuições ativas anteriores
        active_assignments = submission.assignments.filter(status=Assignment.Status.ACTIVE)
        for old in active_assignments:
            old.status = Assignment.Status.REASSIGNED
            old.ended_at = now
            old.reason = reason or "Redistribuição de carga de trabalho"
            old.save(update_fields=["status", "ended_at", "reason"])

        assignment = Assignment.objects.create(
            submission=submission,
            analyst=analyst,
            assigned_by=assigned_by,
            status=Assignment.Status.ACTIVE,
            reason=reason,
            assigned_at=now,
        )

        # Transiciona workflow para ASSIGNED se estiver em RECEIVED
        if submission.workflow_status == Submission.WorkflowStatus.RECEIVED:
            cls.transition(
                submission=submission,
                target_status=Submission.WorkflowStatus.ASSIGNED,
                actor=assigned_by,
                reason=f"Atribuído ao analista {analyst.username}",
            )

        AuditEvent.objects.create(
            actor=assigned_by,
            entity_type="Assignment",
            entity_id=str(assignment.id),
            action="ASSIGN",
            new_value=analyst.username,
            metadata={"processo_sei": submission.processo_sei, "reason": reason},
        )

        return assignment

    @classmethod
    def reassign_analyst(
        cls,
        submission: Submission,
        new_analyst: User,
        assigned_by: User,
        reason: str = "",
    ) -> Assignment:
        """Redistribui uma submissão para um novo analista."""
        return cls.assign_analyst(
            submission=submission,
            analyst=new_analyst,
            assigned_by=assigned_by,
            reason=reason or "Redistribuição de processo",
        )

    @classmethod
    @transaction.atomic
    def on_evaluation_completed(cls, evaluation: Evaluation, actor: User) -> None:
        """Chamado quando o analista conclui sua avaliação documental.

        Cria automaticamente a tarefa de revisão para que o revisor aprove ou divirja.
        """
        submission = evaluation.submission

        if evaluation.result not in (Evaluation.Result.APTA, Evaluation.Result.INAPTA):
            raise ValidationError("Análise em andamento não pode ser concluída.")
        if evaluation.result == Evaluation.Result.APTA:
            cls.transition(
                submission,
                Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
                actor,
                reason="Análise apta concluída.",
            )
            return

        # Only inapt evaluations require a review task.
        cls.transition(
            submission=submission,
            target_status=Submission.WorkflowStatus.PENDING_REVIEW,
            actor=actor,
            reason=f"Análise concluída com parecer '{evaluation.get_result_display()}'.",
        )

        # Garante a existência do registro de Review
        review, created = Review.objects.get_or_create(
            evaluation=evaluation,
            submission=submission,
            defaults={
                "reviewer": None,
                "status": Review.Status.PENDING,
                "preliminary_result": Review.PreliminaryResult.PENDING_DECISION,
            },
        )

        if created:
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Review",
                entity_id=str(review.id),
                action="CREATE_REVIEW_TASK",
                metadata={"processo_sei": submission.processo_sei},
            )

    @classmethod
    @transaction.atomic
    def open_diligence(
        cls,
        submission: Submission,
        requested_by: User,
        reason: str,
        deadline: datetime.date,
        unsatisfied_return_status: str | None = None,
    ) -> Diligence:
        """Abre uma diligência e move o processo para PENDING_DILIGENCE."""
        submission = Submission.objects.select_for_update().get(pk=submission.pk)
        cls.enforce_diligence_actor(submission, requested_by)
        if deadline is None:
            raise ValidationError("Nova diligência exige prazo.")
        origins = {
            Submission.WorkflowStatus.UNDER_ANALYSIS,
            Submission.WorkflowStatus.PENDING_REVIEW,
            Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
            Submission.WorkflowStatus.INELIGIBLE,
        }
        if submission.workflow_status not in origins:
            raise ValidationError("Origem não autorizada para diligência.")
        # A legal failure consequence must be explicitly supplied. Do not assume ineligibility.
        if unsatisfied_return_status is not None and unsatisfied_return_status not in origins:
            raise ValidationError("Consequência inválida para diligência não saneada.")
        diligence = Diligence.objects.create(
            submission=submission,
            requested_by=requested_by,
            reason=reason,
            deadline=deadline,
            requested_at=timezone.now(),
            origin_status=submission.workflow_status,
            unsatisfied_return_status=unsatisfied_return_status or "",
            status=Diligence.Status.OPEN,
            result=Diligence.Result.PENDENTE,
        )

        AuditEvent.objects.create(
            actor=requested_by,
            entity_type="Diligence",
            entity_id=str(diligence.pk),
            action="OPEN_DILIGENCE",
            metadata={"origin_status": diligence.origin_status},
        )

        cls.transition(
            submission=submission,
            target_status=Submission.WorkflowStatus.PENDING_DILIGENCE,
            actor=requested_by,
            reason=f"Diligência aberta: {reason[:100]}",
            metadata={"diligence_id": diligence.id, "deadline": str(deadline)},
        )

        return diligence

    @staticmethod
    def enforce_diligence_actor(submission, actor):
        if actor.is_superuser or actor.role in {User.Role.ADMINISTRADOR, User.Role.COORDENADOR}:
            return
        if (
            actor.role == User.Role.REVISOR
            and submission.reviews.filter(reviewer=actor, status=Review.Status.PENDING).exists()
        ):
            return
        raise PermissionDenied(
            "Diligência exige coordenação ou revisor responsável pela revisão pendente."
        )

    @classmethod
    @transaction.atomic
    def conclude_diligence(
        cls,
        diligence: Diligence,
        actor: User,
        result: str,
        response_text: str = "",
    ) -> Diligence:
        """Conclui a diligência e retorna o processo para o estado adequado de workflow."""
        diligence = (
            Diligence.objects.select_for_update().select_related("submission").get(pk=diligence.pk)
        )
        cls.enforce_diligence_actor(diligence.submission, actor)
        if diligence.status not in (Diligence.Status.OPEN, Diligence.Status.ANSWERED):
            raise ValidationError("Diligência não está aberta/respondida.")
        if result not in (Diligence.Result.SANEADA, Diligence.Result.NAO_SANEADA):
            raise ValidationError("Resultado conclusivo inválido.")
        if result == Diligence.Result.NAO_SANEADA and not diligence.unsatisfied_return_status:
            raise ValidationError(
                "OPEN BUSINESS QUESTION: defina explicitamente a consequência da diligência não saneada."
            )
        if response_text:
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Diligence",
                entity_id=str(diligence.pk),
                action="ANSWER_DILIGENCE",
            )
        diligence.status = Diligence.Status.CONCLUDED
        diligence.result = result
        diligence.concluded_at = timezone.now()
        if response_text:
            diligence.response = response_text
            diligence.answered_at = timezone.now()
        diligence.save()

        submission = diligence.submission
        # Retorno adequado do subfluxo
        if result == Diligence.Result.SANEADA:
            next_status = diligence.origin_status
            reason = (
                "Diligência concluída com êxito (falha saneada). Retornado para análise/revisão."
            )
        else:
            next_status = diligence.unsatisfied_return_status
            reason = "Diligência não saneada ou sem resposta satisfatória."

        cls.transition(
            submission=submission,
            target_status=next_status,
            actor=actor,
            reason=reason,
            metadata={"diligence_id": diligence.id, "diligence_result": result},
        )

        AuditEvent.objects.create(
            actor=actor,
            entity_type="Diligence",
            entity_id=str(diligence.pk),
            action="CONCLUDE_DILIGENCE",
            new_value=result,
        )

        return diligence
