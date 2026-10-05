from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("editais", "0003_edital_duplicate_scope_edital_tie_breaker_policy")]

    operations = [
        # Preserve every existing group rule verbatim. No unsupported G1 -> vacancy conversion.
        migrations.RenameModel(old_name="FundingRule", new_name="LegacyGroupFundingRule"),
        migrations.AlterField(
            model_name="legacygroupfundingrule", name="edital",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="legacy_group_funding_rules", to="editais.edital", verbose_name="Edital"),
        ),
        migrations.AddField(
            model_name="edital", name="minimum_equity_percentage",
            field=models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"), validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)]),
        ),
        migrations.CreateModel(
            name="FundingRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vacancy_type", models.CharField(max_length=20, choices=[("FEMALE", "Feminina"), ("MALE", "Masculina"), ("NURSING_MOTHER", "Mãe nutriz")])),
                ("monthly_value", models.DecimalField(max_digits=12, decimal_places=2, validators=[django.core.validators.MinValueValidator(0)])),
                ("duration_months", models.PositiveIntegerField(default=12, validators=[django.core.validators.MinValueValidator(1)])),
                ("edital", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="funding_rules", to="editais.edital")),
            ],
            options={"db_table": "editais_vacancy_funding_rule", "constraints": [models.UniqueConstraint(fields=("edital", "vacancy_type"), name="unique_funding_vacancy_type")]},
        ),
    ]
