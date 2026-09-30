"""Semantic status assessment, without requirement codes or external schemas."""

from apps.editais.models import Requirement
from apps.editais.selectors import active_requirement_checks


def definition_rows(evaluation):
    results = list(evaluation.check_results.select_related("requirement_check", "requirement"))
    checks = {cr.requirement_check_id: cr for cr in results if cr.requirement_check_id}
    direct = {cr.requirement_id: cr for cr in results if cr.requirement_check_id is None}
    rows = []
    for requirement in Requirement.objects.filter(
        edital=evaluation.submission.edital, active=True
    ).prefetch_related("checks__validation_rules"):
        definitions = active_requirement_checks(requirement)
        if definitions:
            for c in definitions:
                result = checks.get(c.pk)
                if result:
                    result.requirement_check = c
                    result.requirement = requirement
                    result.evaluation = evaluation
                rows.append((requirement, c, result))
        else:
            result = direct.get(requirement.pk)
            if result:
                result.requirement = requirement
                result.evaluation = evaluation
            rows.append((requirement, requirement, result))
    return rows


def is_required(requirement, definition):
    return (
        requirement.mandatory
        and getattr(definition, "required", True)
        and getattr(definition, "contributes_to_result", True)
    )


def status_rules(definition):
    return (
        definition.accepted_statuses or ["ATENDE", "NAO_APLICAVEL"],
        definition.failure_statuses or ["NAO_ATENDE", "NAO_ENVIADO"],
    )


def blocking_results(evaluation):
    return [
        result
        for req, definition, result in definition_rows(evaluation)
        if result and is_required(req, definition) and result.status in status_rules(definition)[1]
    ]


def assess(evaluation, overrides=None, rows=None):
    overrides = overrides or {}
    failed_codes, blocking, pending, evaluated = set(), False, 0, 0
    rows = definition_rows(evaluation) if rows is None else rows
    for req, definition, result in rows:
        status = overrides.get(result.pk, result.status) if result else "EM_BRANCO"
        accepted, failures = status_rules(definition)
        if status != "EM_BRANCO":
            evaluated += 1
        if req.mandatory and getattr(definition, "required", True) and status in failures:
            failed_codes.add(req.code)
        if not is_required(req, definition):
            continue
        if status in {"EM_BRANCO", "NAO_ENVIADO"} or status not in {*accepted, *failures}:
            pending += 1
        if status in failures:
            blocking = True
    return {
        "result": "INAPTA" if blocking else "APTA" if pending == 0 and rows else "EM_ANALISE",
        "failed_requirement_codes": sorted(failed_codes),
        "total_checks": len(rows),
        "evaluated_checks": evaluated,
        "pending_checks": pending,
        "is_complete": bool(rows) and pending == 0,
    }
