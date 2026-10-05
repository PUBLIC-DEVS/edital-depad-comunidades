from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models

from .immutability import AppendOnlyQuerySet


class AuditEvent(models.Model):
    """Registro append-only de eventos de auditoria e rastreabilidade no sistema.

    Evitamos GenericForeignKey em favor de campos explícitos de entity_type e entity_id
    (strings), o que simplifica migrações, evita joins polimórficos caros e desacopla
    o histórico permanente de auditoria contra exclusões lógicas ou refatorações de modelos.
    """

    objects = AppendOnlyQuerySet.as_manager()

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
        verbose_name="Usuário Responsável",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Data/Hora do Evento",
    )
    entity_type = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="Tipo da Entidade",
        help_text="Nome da classe ou domínio afetado (ex: Submission, Evaluation, Review).",
    )
    entity_id = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="ID da Entidade",
    )
    action = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Ação Executada",
        help_text="Ex: CREATE, UPDATE, TRANSITION, ASSIGN, DILIGENCE_OPENED, RANKING_SNAPSHOT.",
    )
    field = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Campo Alterado",
    )
    old_value = models.TextField(
        blank=True,
        verbose_name="Valor Anterior",
    )
    new_value = models.TextField(
        blank=True,
        verbose_name="Novo Valor",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadados Adicionais",
    )

    class Meta:
        verbose_name = "Evento de Auditoria"
        verbose_name_plural = "Eventos de Auditoria"
        ordering = ["-timestamp"]

    def __str__(self):
        actor_name = self.actor.username if self.actor else "SISTEMA"
        ts = f"{self.timestamp:%d/%m/%Y %H:%M:%S}"
        return f"[{ts}] {actor_name} -> {self.action} on {self.entity_type}#{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            msg = "Registros de auditoria são estritamente append-only e não podem ser alterados."
            raise PermissionDenied(msg)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Registros de auditoria não podem ser excluídos.")
