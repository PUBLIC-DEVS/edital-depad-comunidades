from django.db import models


class LegacyImportRun(models.Model):
    source_filename = models.CharField(max_length=255)
    source_sha256 = models.CharField(max_length=64, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=20, default="RUNNING")
    edital = models.ForeignKey("editais.Edital", on_delete=models.PROTECT, null=True)
    total_rows = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    mode = models.CharField(max_length=10, default="strict")


class LegacyImportIssue(models.Model):
    run = models.ForeignKey(LegacyImportRun, on_delete=models.CASCADE, related_name="issues")
    severity = models.CharField(max_length=10)
    sheet = models.CharField(max_length=100)
    row = models.PositiveIntegerField(null=True)
    column = models.CharField(max_length=10, blank=True)
    processo_sei = models.CharField(max_length=50, blank=True)
    code = models.CharField(max_length=80)
    message = models.TextField()
    raw_value = models.JSONField(null=True)


class LegacySourceRecord(models.Model):
    """Source observations, separate from operational entities.

    Every run retains original cells and formulas; no historical operational date is inferred
    from this record's ingestion time. One row can document multiple derived entities.
    """

    run = models.ForeignKey(LegacyImportRun, on_delete=models.CASCADE, related_name="records")
    sheet = models.CharField(max_length=100)
    row = models.PositiveIntegerField()
    processo_sei = models.CharField(max_length=50, blank=True)
    raw_values = models.JSONField(default=dict)
    formulas = models.JSONField(default=dict)
    entities = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "sheet", "row"], name="unique_legacy_run_sheet_row"
            )
        ]


class LegacyEntityLink(models.Model):
    """Stable idempotency key for repeated historical events (including repeated SEIs)."""

    edital = models.ForeignKey("editais.Edital", on_delete=models.PROTECT)
    source_sha256 = models.CharField(max_length=64)
    sheet = models.CharField(max_length=100)
    row = models.PositiveIntegerField()
    entity_type = models.CharField(max_length=50)
    entity_id = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["edital", "source_sha256", "sheet", "row", "entity_type"],
                name="unique_legacy_entity_source",
            )
        ]
