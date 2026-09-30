from django.core.exceptions import ValidationError

from apps.audit.models import AuditEvent
from apps.institutions.cnpj import cnpj_validator, normalize_cnpj

EVIDENCE_FIELDS = (
    "sei_number",
    "pages",
    "document_cnpj",
    "valid_until",
    "opened_on",
    "cnae",
    "canonical_cnpj_confirmed",
    "numeric_value",
    "notes",
)


def audit_value(value):
    return "" if value is None else str(value)


def update_result(evaluation, payload, actor):
    results = evaluation.check_results.select_related("requirement_check", "requirement")
    if payload.get("check_result_id"):
        result = results.filter(pk=payload["check_result_id"]).first()
    elif payload.get("requirement_check_id"):
        result = results.filter(requirement_check_id=payload["requirement_check_id"]).first()
    elif payload.get("requirement_id"):
        result = results.filter(
            requirement_id=payload["requirement_id"], requirement_check__isnull=True
        ).first()
    else:
        result = None
    if result is None:
        raise ValidationError("Item não pertence a esta avaliação.")
    definition = result.definition
    allowed = set(definition.allowed_statuses) | {"EM_BRANCO"}
    if result.status != "NAO_ENVIADO":
        allowed.discard("NAO_ENVIADO")
    if payload.get("status", result.status) not in allowed:
        raise ValidationError("Resultado não permitido para este item.")
    values = {name: payload[name] for name in ("status", *EVIDENCE_FIELDS) if name in payload}
    for name in EVIDENCE_FIELDS:
        if name in values and name not in definition.evidence_fields:
            if values[name] not in (None, ""):
                raise ValidationError(f"Evidência {name} não está configurada para este item.")
            del values[name]
    if values.get("document_cnpj"):
        cnpj_validator(values["document_cnpj"])
        values["document_cnpj"] = normalize_cnpj(values["document_cnpj"])
    old_values = {name: getattr(result, name) for name in values}
    for name, value in values.items():
        setattr(result, name, value)
    result.full_clean()
    changed = {
        name: (old, getattr(result, name))
        for name, old in old_values.items()
        if old != getattr(result, name)
    }
    if changed:
        result.save(update_fields=[*changed, "updated_at"])
        for name, (old, new) in changed.items():
            AuditEvent.objects.create(
                actor=actor,
                entity_type="CheckResult",
                entity_id=str(result.pk),
                action="FIELD_CHANGE",
                field=name,
                old_value=audit_value(old),
                new_value=audit_value(new),
                metadata={"evaluation_id": evaluation.pk, "requirement_id": result.requirement_id},
            )
    return result
