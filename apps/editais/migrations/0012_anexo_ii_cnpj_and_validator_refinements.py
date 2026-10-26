from django.db import migrations


def upgrade_anexo_ii_and_validators(apps, schema_editor):
    RequirementCheck = apps.get_model("editais", "RequirementCheck")
    RequirementValidationRule = apps.get_model("editais", "RequirementValidationRule")

    for check in RequirementCheck.objects.filter(code="FICHA_CADASTRAL"):
        if not check.collect_document_cnpj:
            check.collect_document_cnpj = True
            check.save(update_fields=["collect_document_cnpj"])
        RequirementValidationRule.objects.get_or_create(
            requirement_check=check,
            rule_type="CNPJ_MATCH_CANONICAL",
            defaults={
                "severity": "WARNING",
                "blocks_completion": False,
                "config": {},
                "order": 1,
                "active": True,
            },
        )

    RequirementValidationRule.objects.filter(blocks_completion=True).update(blocks_completion=False)

    for rule in RequirementValidationRule.objects.filter(rule_type="CNAE_REQUIRED"):
        config = dict(rule.config) if isinstance(rule.config, dict) else {}
        if config.get("match_mode") == "UNRESOLVED":
            config["match_mode"] = "CONTAINS"
            rule.config = config
            rule.save(update_fields=["config"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("editais", "0011_alter_edital_duplicate_policy"),
    ]

    operations = [
        migrations.RunPython(upgrade_anexo_ii_and_validators, noop_reverse),
    ]
