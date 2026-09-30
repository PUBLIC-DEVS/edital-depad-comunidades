"""Publish minimal controlled fixtures through the ordinary audited service."""

from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import ClassificationPolicy, ProgramMunicipality, Requirement, TargetGroup
from apps.editais.services import EditalConfigurationService


def publish_fixture(edital):
    if edital.status == "ACTIVE":
        return edital
    edital.closes_at = edital.opens_at + timezone.timedelta(days=30)
    edital.requires_financial_rules = False
    edital.save()
    if not edital.target_groups.exists():
        TargetGroup.objects.create(
            edital=edital, code="G1", name="G1", vacancy_types=["FEMALE", "MALE", "NURSING_MOTHER"]
        )
        ClassificationPolicy.objects.create(edital=edital)
    if not edital.requirements.exists():
        Requirement.objects.create(
            edital=edital, code="DOC", name="Documento", requires_checks=False
        )
    for check in edital.requirements.all():
        for criterion in check.checks.all():
            if not criterion.code:
                criterion.code = f"ITEM-{criterion.pk}"
                criterion.save()
    for group in edital.target_groups.exclude(program=None):
        from apps.institutions.models import Municipality

        municipality = Municipality.objects.first()
        if municipality:
            ProgramMunicipality.objects.get_or_create(
                edital=edital, program=group.program, municipality=municipality
            )
    actor, _ = User.objects.get_or_create(
        username="fixture-publisher", defaults={"role": "ADMINISTRADOR"}
    )
    if not User.objects.filter(role="REVISOR", is_active=True).exists():
        User.objects.create_user(username="fixture-reviewer", role="REVISOR")
    EditalConfigurationService.publish(edital, actor)
    edital.refresh_from_db()
    return edital
