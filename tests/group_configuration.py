"""Explicit policy fixtures for existing group scenarios, never a runtime default."""

from apps.editais.models import ClassificationPolicy, Program, TargetGroup


def configure_example_groups(edital):
    program, _ = Program.objects.get_or_create(code="PRONASCI", defaults={"name": "PRONASCI"})
    for order, code, types, group_program in [
        (1, "G1", ["FEMALE", "NURSING_MOTHER"], None),
        (2, "G2", ["MALE"], program),
        (3, "G3", ["MALE"], None),
    ]:
        TargetGroup.objects.create(
            edital=edital,
            code=code,
            name=code,
            order=order,
            vacancy_types=types,
            program=group_program,
        )
    ClassificationPolicy.objects.create(edital=edital)
    return program
