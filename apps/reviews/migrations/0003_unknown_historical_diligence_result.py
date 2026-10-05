from django.db import migrations, models


def clarify_unknown_results(apps, schema_editor):
    Diligence = apps.get_model("reviews", "Diligence")
    AuditEvent = apps.get_model("audit", "AuditEvent")
    alias = schema_editor.connection.alias
    for event in Diligence.objects.using(alias).filter(status="LEGACY_UNKNOWN", result="PENDENTE").iterator():
        event.result = "LEGACY_UNKNOWN"
        event.save(using=alias, update_fields=["result"])
        AuditEvent.objects.using(alias).create(
            entity_type="Diligence", entity_id=str(event.pk), action="LEGACY_RESULT_CLARIFIED",
            field="result", old_value="PENDENTE", new_value="LEGACY_UNKNOWN",
            metadata={"migration": "reviews.0003", "reason": "No historical operational outcome inferred"},
        )


class Migration(migrations.Migration):
    dependencies = [("reviews", "0002_diligence_origin_status_and_more"), ("audit", "0001_initial")]
    operations = [
        migrations.AlterField(
            model_name="diligence", name="result",
            field=models.CharField(max_length=20, default="PENDENTE", verbose_name="Resultado da Diligência",
                choices=[("LEGACY_UNKNOWN", "Histórico: resultado operacional desconhecido"),
                         ("PENDENTE", "Pendente de Julgamento"), ("SANEADA", "Falha Saneada / Acolhida"),
                         ("NAO_SANEADA", "Não Saneada / Mantida Inaptidão")]),
        ),
        migrations.RunPython(clarify_unknown_results, reverse_code=migrations.RunPython.noop),
    ]
