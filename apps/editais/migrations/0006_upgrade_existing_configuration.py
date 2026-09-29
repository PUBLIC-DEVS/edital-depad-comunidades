from django.db import migrations


def upgrade(apps, schema_editor):
    Edital = apps.get_model("editais", "Edital")
    Program = apps.get_model("editais", "Program")
    Link = apps.get_model("editais", "ProgramMunicipality")
    Group = apps.get_model("editais", "TargetGroup")
    Policy = apps.get_model("editais", "ClassificationPolicy")
    Check = apps.get_model("editais", "RequirementCheck")
    Result = apps.get_model("evaluations", "CheckResult")
    Submission = apps.get_model("submissions", "Submission")
    Event = apps.get_model("audit", "AuditEvent")
    for link in Link.objects.all().iterator():
        program, _ = Program.objects.get_or_create(code=link.program_name, defaults={"name": link.program_name})
        link.program = program
        link.save(update_fields=["program"])
    for edital in Edital.objects.all().iterator():
        mapped = {"PUBLISHED": "ACTIVE", "IN_PROGRESS": "ACTIVE", "SUSPENDED": "CLOSED"}.get(edital.status)
        if mapped:
            Event.objects.create(entity_type="Edital", entity_id=str(edital.pk), action="CONFIG_MIGRATION", field="status", old_value=edital.status, new_value=mapped)
            edital.status = mapped
            edital.save(update_fields=["status"])
        program = Program.objects.filter(code="PRONASCI").first()
        definitions = [("G1", "Feminino e mães nutrizes", ["FEMALE", "NURSING_MOTHER"], None), ("G2", "Masculino no programa prioritário", ["MALE"], program), ("G3", "Masculino", ["MALE"], None)]
        for order, (code, name, types, program) in enumerate(definitions, 1):
            if code == "G2" and program is None:
                program, _ = Program.objects.get_or_create(code="PRONASCI", defaults={"name": "PRONASCI"})
            Group.objects.get_or_create(edital=edital, code=code, defaults={"name": name, "order": order, "vacancy_types": types, "program": program})
        Policy.objects.get_or_create(edital=edital)
        for group in Group.objects.filter(edital=edital):
            Submission.objects.filter(edital=edital, target_group=group.code).update(target_group_definition=group)
    # Keep every pre-existing evidence field visible. New definitions use contextual defaults.
    Check.objects.all().update(collect_document_cnpj=True, collect_valid_until=True, collect_numeric_value=True)
    for check in Check.objects.all().iterator():
        Result.objects.filter(requirement_check_id=check.pk).update(requirement_id=check.requirement_id)


def reverse_statuses(apps, schema_editor):
    Edital = apps.get_model("editais", "Edital")
    Event = apps.get_model("audit", "AuditEvent")
    for event in Event.objects.filter(entity_type="Edital", action="CONFIG_MIGRATION", field="status"):
        Edital.objects.filter(pk=event.entity_id, status=event.new_value).update(status=event.old_value)


class Migration(migrations.Migration):
    dependencies = [
        ("editais", "0005_program_edital_cloned_from_edital_description_and_more"),
        ("evaluations", "0003_checkresult_requirement_and_more"),
        ("submissions", "0005_submission_target_group_definition_and_more"),
        ("audit", "0001_initial"),
    ]
    operations = [migrations.RunPython(upgrade, reverse_statuses)]
