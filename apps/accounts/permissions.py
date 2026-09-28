"""Camada centralizada de Autorização, RBAC e Políticas de Segregação (Selectors & Policies)."""

from functools import wraps
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from apps.evaluations.models import Evaluation
from apps.reviews.models import Review
from apps.submissions.models import Assignment, Submission


class RolePermissionPolicy:
    """Políticas de autorização por papel institucional (RBAC)."""

    @staticmethod
    def can_view_all_submissions(user: User) -> bool:
        """Coordenadores, Distribuidores, Administradores e Consulta veem o conjunto completo."""
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        allowed_roles = {
            User.Role.ADMINISTRADOR,
            User.Role.COORDENADOR,
            User.Role.DISTRIBUIDOR,
            User.Role.CONSULTA,
        }
        return user.role in allowed_roles

    @staticmethod
    def can_distribute_submissions(user: User) -> bool:
        """Apenas Distribuidores, Coordenadores e Administradores podem distribuir ou redistribuir."""
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role in {User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR}

    @staticmethod
    def can_generate_ranking(user: User) -> bool:
        """Apenas Coordenadores e Administradores podem gerar snapshots de ranking."""
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role in {User.Role.COORDENADOR, User.Role.ADMINISTRADOR}

    @staticmethod
    def can_manage_editais_and_rules(user: User) -> bool:
        """Apenas Administradores têm permissão de configuração de editais e critérios."""
        if not user.is_authenticated:
            return False
        return user.is_superuser or user.role == User.Role.ADMINISTRADOR

    @staticmethod
    def can_conduct_review(user: User) -> bool:
        """Apenas Revisores, Coordenadores e Administradores podem atuar na fila de revisão."""
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.role in {User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR}

    @classmethod
    def can_access_submission(cls, user: User, submission: Submission) -> bool:
        """Verifica se o usuário pode acessar/visualizar uma submissão específica."""
        if not user.is_authenticated:
            return False
        if cls.can_view_all_submissions(user):
            return True
        if user.role == User.Role.ANALISTA:
            # Analista só acessa se estiver atribuído a ele com status ativo
            return submission.assignments.filter(
                analyst=user,
                status=Assignment.Status.ACTIVE,
            ).exists()
        if user.role == User.Role.REVISOR:
            # Revisor acessa se houver revisão ativa ou pendente
            return (
                submission.reviews.exists()
                or submission.workflow_status == Submission.WorkflowStatus.PENDING_REVIEW
            )
        return False

    @staticmethod
    def can_edit_evaluation(user: User, evaluation: Evaluation) -> bool:
        """Analista só pode editar sua própria avaliação enquanto ela estiver em rascunho (DRAFT)."""
        if not user.is_authenticated:
            return False
        # Administrador ou superusuário pode auditar, mas alteração operacional é do analista
        if user.role == User.Role.ANALISTA:
            if evaluation.analyst_id != user.id:
                return False
            # Não pode editar avaliação já concluída
            return evaluation.status == Evaluation.Status.DRAFT
        if user.is_superuser:
            return True
        return False

    @staticmethod
    def can_edit_review(user: User, review: Review) -> bool:
        """Revisor só pode editar sua própria revisão enquanto pendente."""
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if user.role in {User.Role.REVISOR, User.Role.COORDENADOR}:
            return review.status == Review.Status.PENDING
        return False


class ScopedQuerySetSelector:
    """Centraliza a segregação de escopo de dados no banco de dados por usuário logado."""

    @staticmethod
    def for_submissions(user: User, queryset: QuerySet | None = None) -> QuerySet[Submission]:
        """Filtra o queryset de submissões de acordo com o papel do usuário."""
        if queryset is None:
            queryset = Submission.objects.all()

        if not user.is_authenticated:
            return queryset.none()

        if RolePermissionPolicy.can_view_all_submissions(user):
            return queryset

        if user.role == User.Role.ANALISTA:
            # Analista vê exclusivamente os processos atribuídos a ele
            return queryset.filter(
                assignments__analyst=user,
                assignments__status=Assignment.Status.ACTIVE,
            ).distinct()

        if user.role == User.Role.REVISOR:
            # Revisor vê processos em revisão ou que possuam revisão
            return queryset.filter(
                workflow_status__in=[
                    Submission.WorkflowStatus.PENDING_REVIEW,
                    Submission.WorkflowStatus.PENDING_DILIGENCE,
                    Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
                    Submission.WorkflowStatus.INELIGIBLE,
                ]
            ).distinct()

        return queryset.none()

    @staticmethod
    def for_evaluations(user: User, queryset: QuerySet | None = None) -> QuerySet[Evaluation]:
        """Filtra avaliações permitidas para o usuário."""
        if queryset is None:
            queryset = Evaluation.objects.all()

        if not user.is_authenticated:
            return queryset.none()

        if user.is_superuser or user.role in {User.Role.COORDENADOR, User.Role.ADMINISTRADOR}:
            return queryset

        if user.role == User.Role.ANALISTA:
            return queryset.filter(analyst=user)

        if user.role == User.Role.REVISOR:
            return queryset.filter(
                submission__workflow_status__in=[
                    Submission.WorkflowStatus.PENDING_REVIEW,
                    Submission.WorkflowStatus.PENDING_DILIGENCE,
                ]
            )

        return queryset.none()


def require_role(*roles: str):
    """Decorator para views exigindo determinados papéis de usuário."""
    if len(roles) == 1 and isinstance(roles[0], (list, tuple, set)):
        roles = tuple(roles[0])

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any):
            if not request.user.is_authenticated:
                raise PermissionDenied("Autenticação necessária.")
            if request.user.is_superuser or request.user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied(f"Acesso restrito aos perfis: {', '.join(roles)}.")

        return _wrapped

    return decorator


def enforce_submission_access(request: HttpRequest, submission_id: int) -> Submission:
    """Obtém a submissão e garante que o usuário autenticado tenha permissão de acesso."""
    submission = get_object_or_404(Submission, id=submission_id)
    if not RolePermissionPolicy.can_access_submission(request.user, submission):
        raise PermissionDenied("Acesso negado: você não tem permissão para acessar este processo.")
    return submission


def enforce_evaluation_edit_access(request: HttpRequest, evaluation_id: int) -> Evaluation:
    """Obtém a avaliação e garante que o usuário possa editá-la."""
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    if not RolePermissionPolicy.can_edit_evaluation(request.user, evaluation):
        raise PermissionDenied("Acesso negado: você não tem permissão para editar esta análise.")
    return evaluation
