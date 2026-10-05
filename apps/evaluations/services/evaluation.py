"""Serviço de Domínio para Avaliação Documental de Editais."""

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import EditalConfigurationSnapshot, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.submissions.models import Submission


class EvaluationError(Exception):
    """Exceção base para erros na camada de avaliação."""


class InconsistentEvaluationError(EvaluationError):
    """Lançada quando a avaliação possui inconsistências impeditivas para conclusão."""


@dataclass(frozen=True)
class EvaluationAssessment:
    """Resultado imutável do cálculo das checagens documentais."""

    result: str  # Evaluation.Result: APTA, INAPTA ou EM_ANALISE
    failed_requirement_codes: list[str]
    total_checks: int
    evaluated_checks: int
    pending_checks: int
    is_complete: bool


class EvaluationService:
    """Serviço responsável pela execução, cálculo de conformidade e conclusão de análises documentais."""

    @staticmethod
    def calculate_assessment(evaluation, status_overrides=None, rows=None):
        from apps.evaluations.assessment import assess

        return EvaluationAssessment(**assess(evaluation, status_overrides, rows))

    @staticmethod
    def blocking_check_results(evaluation):
        from apps.evaluations.assessment import blocking_results

        return blocking_results(evaluation)

    @classmethod
    @transaction.atomic
    def initialize_evaluation(cls, submission: Submission, analyst: User) -> Evaluation:
        """Inicializa ou obtém a avaliação de uma submissão, gerando registros de checagem em branco."""
        from apps.submissions.services.eligibility import ParticipationEligibilityService

        ParticipationEligibilityService.require_assignable(submission)
        evaluation, created = Evaluation.objects.get_or_create(
            submission=submission,
            defaults={
                "analyst": analyst,
                "status": Evaluation.Status.DRAFT,
                "result": Evaluation.Result.EM_ANALISE,
                "started_at": timezone.now(),
                "configuration_snapshot": EditalConfigurationSnapshot.objects.filter(
                    edital=submission.edital
                )
                .order_by("pk")
                .last(),
            },
        )
        if evaluation.analyst_id != analyst.pk:
            raise PermissionDenied("Avaliação pertence a outro analista.")

        # Se já existia mas não possuía checks criados, inicializa
        checks = RequirementCheck.objects.filter(
            requirement__edital=submission.edital,
            requirement__active=True,
            active=True,
        )
        existing_check_ids = set(
            evaluation.check_results.values_list("requirement_check_id", flat=True)
        )

        to_create = [
            CheckResult(
                evaluation=evaluation,
                requirement_check=c,
                requirement=c.requirement,
                status=CheckResult.Status.EM_BRANCO,
            )
            for c in checks
            if c.id not in existing_check_ids
        ]
        if to_create:
            CheckResult.objects.bulk_create(to_create)

        for req in Requirement.objects.filter(edital=submission.edital, active=True):
            if not req.checks.filter(active=True).exists():
                CheckResult.objects.get_or_create(
                    evaluation=evaluation, requirement=req, requirement_check=None
                )

        if created:
            AuditEvent.objects.create(
                actor=analyst,
                entity_type="Evaluation",
                entity_id=str(evaluation.id),
                action="INITIALIZE",
                new_value=Evaluation.Status.DRAFT,
                metadata={"processo_sei": submission.processo_sei},
            )

        return evaluation

    @classmethod
    @transaction.atomic
    def start_evaluation(cls, submission, analyst):
        submission = Submission.objects.select_for_update().get(pk=submission.pk)
        if analyst.role != User.Role.ANALISTA or submission.assigned_analyst != analyst:
            raise PermissionDenied("Somente o analista atribuído pode iniciar análise.")
        if submission.workflow_status != Submission.WorkflowStatus.ASSIGNED:
            raise ValidationError("Processo não está no estágio de início da análise.")
        from apps.submissions.services.eligibility import ParticipationEligibilityService

        ParticipationEligibilityService.require_assignable(submission)
        evaluation = cls.initialize_evaluation(submission, analyst)
        from apps.submissions.services.workflow import WorkflowService

        WorkflowService.transition(
            submission,
            Submission.WorkflowStatus.UNDER_ANALYSIS,
            analyst,
            reason="Análise iniciada por POST.",
        )
        return evaluation

    @staticmethod
    def enforce_edit(evaluation, actor):
        from apps.accounts.permissions import RolePermissionPolicy

        if not RolePermissionPolicy.can_edit_evaluation(actor, evaluation):
            raise PermissionDenied("Análise não pode ser editada por este usuário.")

    @classmethod
    @transaction.atomic
    def save_draft(
        cls,
        evaluation: Evaluation,
        check_payloads: list[dict[str, Any]],
        actor: User,
        general_notes: str | None = None,
    ) -> EvaluationAssessment:
        """Salva rascunho de preenchimento das checagens sem exigir que todas estejam finalizadas."""
        evaluation = Evaluation.objects.select_for_update().get(pk=evaluation.pk)
        cls.enforce_edit(evaluation, actor)
        from apps.evaluations.drafts import audit_value, update_result

        for item in check_payloads:
            update_result(evaluation, item, actor)
        if general_notes is not None and evaluation.general_notes != general_notes:
            old_notes = evaluation.general_notes
            evaluation.general_notes = general_notes
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Evaluation",
                entity_id=str(evaluation.pk),
                action="FIELD_CHANGE",
                field="general_notes",
                old_value=audit_value(old_notes),
                new_value=audit_value(general_notes),
            )

        assessment = cls.calculate_assessment(evaluation)
        evaluation.result = assessment.result
        evaluation.failed_requirement_codes = assessment.failed_requirement_codes
        evaluation.save(
            update_fields=["result", "failed_requirement_codes", "general_notes", "updated_at"]
        )

        AuditEvent.objects.create(
            actor=actor,
            entity_type="Evaluation",
            entity_id=str(evaluation.id),
            action="SAVE_DRAFT",
            new_value=assessment.result,
            metadata={
                "evaluated_checks": assessment.evaluated_checks,
                "pending_checks": assessment.pending_checks,
            },
        )
        return assessment

    @staticmethod
    def is_reopenable(evaluation: Evaluation) -> bool:
        """Indica (sem efeitos colaterais) se uma análise concluída pode ser reaberta agora.

        Espelha os guardrails de reopen_evaluation para controlar a exibição do botão.
        """
        if evaluation.status != Evaluation.Status.COMPLETED:
            return False
        from apps.reviews.models import Review
        from apps.submissions.services.workflow import WorkflowService

        current = evaluation.submission.workflow_status
        target = Submission.WorkflowStatus.UNDER_ANALYSIS
        if current != target and target not in WorkflowService.ALLOWED_TRANSITIONS.get(
            current, set()
        ):
            return False
        review = Review.objects.filter(evaluation=evaluation).first()
        if review and (review.status != Review.Status.PENDING or review.reviewer_id is not None):
            return False
        return True

    @classmethod
    @transaction.atomic
    def reopen_evaluation(cls, evaluation: Evaluation, actor: User) -> Evaluation:
        """Reabre uma análise concluída, devolvendo-a ao estágio de rascunho para edição.

        Permite ao analista responsável (ou à coordenação) corrigir um registro antigo.
        A operação é restrita para preservar a integridade do fluxo: só é possível quando
        o processo ainda pode retornar para "Em Análise" e nenhuma revisão foi iniciada.
        """
        from apps.accounts.permissions import RolePermissionPolicy
        from apps.reviews.models import Review
        from apps.submissions.services.workflow import WorkflowService

        evaluation = (
            Evaluation.objects.select_for_update()
            .select_related("submission")
            .get(pk=evaluation.pk)
        )
        if not RolePermissionPolicy.can_reopen_evaluation(actor, evaluation):
            raise PermissionDenied("Você não tem permissão para reabrir esta análise.")
        if evaluation.status != Evaluation.Status.COMPLETED:
            raise ValidationError("Apenas análises concluídas podem ser reabertas.")

        submission = Submission.objects.select_for_update().get(pk=evaluation.submission_id)
        current = submission.workflow_status
        target = Submission.WorkflowStatus.UNDER_ANALYSIS

        # Bloqueia se uma revisão já foi atribuída ou concluída: nesse caso a reabertura
        # depende da coordenação para não descartar trabalho de revisão em andamento.
        review = Review.objects.filter(evaluation=evaluation).first()
        if review and (
            review.status != Review.Status.PENDING or review.reviewer_id is not None
        ):
            raise ValidationError(
                "Já existe revisão atribuída ou concluída para esta análise; "
                "a reabertura precisa ser tratada pela coordenação."
            )

        needs_transition = current != target
        if needs_transition and target not in WorkflowService.ALLOWED_TRANSITIONS.get(
            current, set()
        ):
            raise ValidationError(
                "A reabertura não é permitida no estágio atual do processo "
                f"({submission.get_workflow_status_display()}). Solicite à coordenação."
            )

        evaluation.status = Evaluation.Status.DRAFT
        evaluation.completed_at = None
        evaluation.save(update_fields=["status", "completed_at", "updated_at"])

        if needs_transition:
            WorkflowService.transition(
                submission,
                target,
                actor,
                reason="Reabertura da análise para edição pelo responsável.",
            )

        # Remove a tarefa de revisão pendente não atribuída, evitando um registro órfão.
        if review:
            review_id = review.id
            review.delete()
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Review",
                entity_id=str(review_id),
                action="CANCEL_REVIEW_TASK",
                metadata={"reason": "Reabertura da análise pelo analista responsável."},
            )

        AuditEvent.objects.create(
            actor=actor,
            entity_type="Evaluation",
            entity_id=str(evaluation.id),
            action="REOPEN",
            old_value=Evaluation.Status.COMPLETED,
            new_value=Evaluation.Status.DRAFT,
            metadata={"processo_sei": submission.processo_sei},
        )
        return evaluation

    @classmethod
    @transaction.atomic
    def conclude_evaluation(
        cls,
        evaluation: Evaluation,
        actor: User,
        notes: str = "",
    ) -> Evaluation:
        """Conclui a avaliação documental e avança o workflow para revisão ou elegibilidade.

        Valida que não existem checagens pendentes em branco antes de permitir conclusão.
        """
        evaluation = (
            Evaluation.objects.select_for_update()
            .select_related("submission")
            .get(pk=evaluation.pk)
        )
        cls.enforce_edit(evaluation, actor)
        assessment = cls.calculate_assessment(evaluation)

        if not assessment.is_complete:
            msg = f"Existem {assessment.pending_checks} itens obrigatórios ainda não avaliados (pendentes)."
            raise InconsistentEvaluationError(msg)
        # Human documentary checks are authoritative. Declarative validators remain
        # available as supporting alerts, including their historical configuration.

        evaluation.status = Evaluation.Status.COMPLETED
        evaluation.result = assessment.result
        evaluation.failed_requirement_codes = assessment.failed_requirement_codes
        evaluation.completed_at = timezone.now()
        if notes:
            evaluation.general_notes = notes
        evaluation.save()

        # Importa WorkflowService para transicionar o workflow da submissão
        from apps.submissions.services.workflow import WorkflowService

        WorkflowService.on_evaluation_completed(evaluation=evaluation, actor=actor)

        AuditEvent.objects.create(
            actor=actor,
            entity_type="Evaluation",
            entity_id=str(evaluation.id),
            action="CONCLUDE",
            old_value=Evaluation.Status.DRAFT,
            new_value=Evaluation.Status.COMPLETED,
            metadata={
                "result": evaluation.result,
                "failed_requirements": evaluation.failed_requirement_codes,
            },
        )

        return evaluation
