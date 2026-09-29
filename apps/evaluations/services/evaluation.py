"""Serviço de Domínio para Avaliação Documental de Editais."""

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Requirement, RequirementCheck
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
    def calculate_assessment(evaluation: Evaluation) -> EvaluationAssessment:
        """Calcula o resultado da avaliação com base nas checagens documentais registradas.

        Regra de Domínio:
        1. Se qualquer requisito OBRIGATÓRIO contiver checagem com status NAO_ATENDE ou NAO_ENVIADO
           -> O requisito é considerado reprovado.
        2. Se houver ao menos um requisito reprovado -> INAPTA (com lista explícita dos códigos reprovados).
        3. Se todos os requisitos obrigatórios estiverem atendidos (ou NAO_APLICAVEL) e não houver
           checagens pendentes (EM_BRANCO) -> APTA.
        4. Caso contrário (há checagens EM_BRANCO e nenhum requisito reprovado ainda) -> EM_ANALISE.
        """
        edital = evaluation.submission.edital
        requirements = Requirement.objects.filter(edital=edital, active=True).prefetch_related(
            "checks"
        )
        results_by_check_id = {
            cr.requirement_check_id: cr
            for cr in evaluation.check_results.select_related("requirement_check__requirement")
        }

        failed_req_codes: list[str] = []
        result_failed = False
        has_pending = False
        total_checks = 0
        evaluated_checks = 0

        for req in requirements:
            req_checks = [c for c in req.checks.all() if c.active]
            total_checks += len(req_checks)

            req_failed = False
            for check in req_checks:
                res = results_by_check_id.get(check.id)
                st = res.status if res else CheckResult.Status.EM_BRANCO
                accepted = check.accepted_statuses or [
                    CheckResult.Status.ATENDE,
                    CheckResult.Status.NAO_APLICAVEL,
                ]
                failures = check.failure_statuses or [
                    CheckResult.Status.NAO_ATENDE,
                    CheckResult.Status.NAO_ENVIADO,
                ]

                if st == CheckResult.Status.EM_BRANCO:
                    has_pending |= check.contributes_to_result
                else:
                    evaluated_checks += 1

                if req.mandatory and st in (
                    CheckResult.Status.NAO_ATENDE,
                    CheckResult.Status.NAO_ENVIADO,
                ):
                    req_failed = True
                if req.mandatory and check.contributes_to_result:
                    result_failed |= st in failures
                    if st not in accepted and st not in failures:
                        has_pending = True

            if req_failed:
                failed_req_codes.append(req.code)

        if result_failed:
            result = Evaluation.Result.INAPTA
        elif not has_pending and total_checks > 0:
            result = Evaluation.Result.APTA
        else:
            result = Evaluation.Result.EM_ANALISE

        return EvaluationAssessment(
            result=result,
            failed_requirement_codes=sorted(set(failed_req_codes)),
            total_checks=total_checks,
            evaluated_checks=evaluated_checks,
            pending_checks=total_checks - evaluated_checks,
            is_complete=(not has_pending and total_checks > 0),
        )

    @classmethod
    @transaction.atomic
    def initialize_evaluation(cls, submission: Submission, analyst: User) -> Evaluation:
        """Inicializa ou obtém a avaliação de uma submissão, gerando registros de checagem em branco."""
        evaluation, created = Evaluation.objects.get_or_create(
            submission=submission,
            defaults={
                "analyst": analyst,
                "status": Evaluation.Status.DRAFT,
                "result": Evaluation.Result.EM_ANALISE,
                "started_at": timezone.now(),
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
                status=CheckResult.Status.EM_BRANCO,
            )
            for c in checks
            if c.id not in existing_check_ids
        ]
        if to_create:
            CheckResult.objects.bulk_create(to_create)

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
        general_notes: str = "",
    ) -> EvaluationAssessment:
        """Salva rascunho de preenchimento das checagens sem exigir que todas estejam finalizadas."""
        evaluation = Evaluation.objects.select_for_update().get(pk=evaluation.pk)
        cls.enforce_edit(evaluation, actor)
        for item in check_payloads:
            check_id = item.get("requirement_check_id")
            if not check_id:
                continue
            if item.get("status", CheckResult.Status.EM_BRANCO) not in CheckResult.Status.values:
                raise ValidationError("Status de checagem inválido.")
            if not evaluation.check_results.filter(requirement_check_id=check_id).exists():
                raise ValidationError("Checagem não pertence à avaliação.")

            CheckResult.objects.filter(evaluation=evaluation, requirement_check_id=check_id).update(
                status=item.get("status", CheckResult.Status.EM_BRANCO),
                sei_number=item.get("sei_number", ""),
                pages=item.get("pages", ""),
                document_cnpj=item.get("document_cnpj", ""),
                valid_until=item.get("valid_until"),
                numeric_value=item.get("numeric_value"),
                notes=item.get("notes", ""),
            )

        if general_notes:
            evaluation.general_notes = general_notes

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
            msg = (
                f"Não é possível concluir a avaliação com {assessment.pending_checks} "
                "checagens pendentes. Avalie todos os itens ou salve como rascunho."
            )
            raise InconsistentEvaluationError(msg)

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
