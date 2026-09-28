from django.conf import settings
from django.db import models


class RankingSnapshot(models.Model):
    """Snapshot imutável de classificação e ranking em determinado momento ou publicação."""

    class SnapshotType(models.TextChoices):
        PRELIMINAR = "PRELIMINAR", "Resultado Preliminar"
        FINAL = "FINAL", "Resultado Final"
        HOMOLOGADO = "HOMOLOGADO", "Resultado Homologado"

    edital = models.ForeignKey(
        "editais.Edital",
        on_delete=models.PROTECT,
        related_name="ranking_snapshots",
        verbose_name="Edital",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_rankings",
        verbose_name="Gerado por",
    )
    snapshot_type = models.CharField(
        max_length=30,
        choices=SnapshotType.choices,
        default=SnapshotType.PRELIMINAR,
        verbose_name="Tipo de Snapshot",
    )
    rules_version = models.CharField(
        max_length=20,
        verbose_name="Versão das Regras Aplicada",
    )
    duplicate_policy = models.CharField(
        max_length=50,
        verbose_name="Política de Duplicidade Utilizada",
    )
    is_immutable = models.BooleanField(
        default=True,
        verbose_name="Imutável",
        help_text="Garante que snapshots já gerados não possam ser alterados retroativamente.",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Descrição / Justificativa da Geração",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Data de Geração")

    class Meta:
        verbose_name = "Snapshot de Ranking"
        verbose_name_plural = "Snapshots de Ranking"
        ordering = ["-created_at"]

    def __str__(self):
        ed = f"Edital {self.edital.number}/{self.edital.year}"
        date_str = f"{self.created_at:%d/%m/%Y %H:%M}"
        return f"Ranking {self.get_snapshot_type_display()} - {ed} ({date_str})"


class RankingEntry(models.Model):
    """Posição individual de uma submissão dentro de um snapshot de ranking."""

    snapshot = models.ForeignKey(
        RankingSnapshot,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name="Snapshot Pai",
    )
    submission = models.ForeignKey(
        "submissions.Submission",
        on_delete=models.PROTECT,
        related_name="ranking_entries",
        verbose_name="Inscrição Classificada",
    )
    target_group = models.CharField(
        max_length=20,
        verbose_name="Grupo Concorrido",
        help_text="G1, G2, G3 ou SEM_GRUPO",
    )
    position = models.PositiveIntegerField(
        verbose_name="Posição na Fila",
        help_text="Ordem numérica no ranking do grupo.",
    )
    received_at = models.DateTimeField(
        verbose_name="Timestamp de Recebimento",
    )
    total_vacancies = models.PositiveIntegerField(
        default=0,
        verbose_name="Total de Vagas Concorridas",
    )
    is_duplicate_suppressed = models.BooleanField(
        default=False,
        verbose_name="Duplicidade Suprimida?",
        help_text="Verdadeiro caso tenha sido desconsiderada pela política de duplicidade.",
    )
    qualification_status = models.CharField(
        max_length=50,
        verbose_name="Status de Habilitação / Parecer",
    )
    tie_breaker_notes = models.TextField(
        blank=True,
        verbose_name="Critérios de Desempate Aplicados",
    )

    class Meta:
        verbose_name = "Entrada no Ranking"
        verbose_name_plural = "Entradas no Ranking"
        ordering = ["target_group", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "target_group", "position"],
                name="unique_snapshot_group_position",
            ),
        ]

    def __str__(self):
        return f"{self.target_group} - #{self.position}: {self.submission.processo_sei}"
