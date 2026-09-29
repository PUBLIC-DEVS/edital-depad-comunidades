"""HTTP helpers for tests that configure the 2026 edital through product screens."""

from django.urls import reverse

from apps.editais.edital_2026 import DOCUMENTS_2026
from apps.editais.models import Edital, Program, RequirementCheck
from apps.institutions.models import Municipality


def post_ok(client, name, args=(), data=None):
    response = client.post(reverse(name, args=args), data or {})
    assert response.status_code == 302, response.content.decode()
    return response


def configure_2026_through_http(client, number="26", reference_date="2026-06-30"):
    post_ok(
        client,
        "edital-create",
        data={
            "name": "Edital 2026 configurado na interface",
            "number": number,
            "year": 2026,
            "description": "Configuração de teste baseada na especificação funcional.",
            "opens_at": "2026-01-01T09:00",
            "closes_at": "2026-12-31T18:00",
            "rules_version": "2026.1",
            "minimum_equity_percentage": "10.00",
            "validation_reference_date": "",
            "duplicate_policy": "WARN_ONLY",
            "duplicate_scope": "ABSOLUTE",
            "tie_breaker_policy": "SEI_LEXICOGRAPHIC",
        },
    )
    edital = Edital.objects.get(number=number, year=2026)

    post_ok(
        client,
        "program-create",
        data={
            "code": "PRONASCI",
            "name": "PRONASCI",
            "description": "Programa de teste",
            "active": "on",
        },
    )
    program = Program.objects.get(code="PRONASCI")
    for order, code, name, vacancy_types, group_program in [
        (1, "G1", "Gênero Feminino", ["FEMALE", "NURSING_MOTHER"], ""),
        (2, "G2", "PRONASCI", ["MALE"], str(program.pk)),
        (3, "G3", "Gênero Masculino", ["MALE"], ""),
    ]:
        post_ok(
            client,
            "edital-section-create",
            [edital.pk, "grupos"],
            {
                "code": code,
                "name": name,
                "order": order,
                "active": "on",
                "vacancy_types": vacancy_types,
                "program": group_program,
            },
        )
    post_ok(
        client,
        "edital-section-create",
        [edital.pk, "classificacao"],
        {"policy_type": "VACANCY_TARGET_POLICY_V2_MIXED_FIRST", "mixed_group_code": "G1"},
    )

    post_ok(
        client,
        "catalog-create",
        ["municipios"],
        {"ibge_code": "3550308", "name": "São Paulo", "state": "SP"},
    )
    municipality = Municipality.objects.get(ibge_code="3550308")
    post_ok(
        client,
        "edital-section-create",
        [edital.pk, "programas"],
        {"program": program.pk, "municipality": municipality.pk, "active": "on"},
    )

    status_config = {
        "allowed_statuses": ["ATENDE", "NAO_ATENDE"],
        "accepted_statuses": ["ATENDE"],
        "failure_statuses": ["NAO_ATENDE"],
    }
    for order, document in enumerate(DOCUMENTS_2026, 1):
        post_ok(
            client,
            "edital-section-create",
            [edital.pk, "requisitos"],
            {
                "code": document["code"],
                "name": document["name"],
                "description": "",
                "presentation_section": document["section"],
                "order": order,
                "mandatory": "on",
                "requires_checks": "on",
                "failure_behavior": "SEND_TO_REVIEW",
                "active": "on",
                "collect_sei_number": "on",
                "collect_pages": "on",
                "collect_notes": "on",
                **status_config,
            },
        )
        requirement = edital.requirements.get(code=document["code"])
        for check_order, raw_spec in enumerate(document["checks"], 1):
            spec = (
                {"code": raw_spec[0], "name": raw_spec[1]}
                if isinstance(raw_spec, tuple)
                else raw_spec
            )
            evidence = spec.get("evidence", {})
            data = {
                "requirement": requirement.pk,
                "code": spec["code"],
                "name": spec["name"],
                "description": "",
                "order": check_order,
                "active": "on",
                "contributes_to_result": "on",
                "collect_sei_number": "on",
                "collect_pages": "on",
                "collect_notes": "on",
                **status_config,
            }
            if spec.get("required", True):
                data["required"] = "on"
            if evidence.get("document_cnpj"):
                data["collect_document_cnpj"] = "on"
            if evidence.get("valid_until"):
                data["collect_valid_until"] = "on"
            if evidence.get("opened_on"):
                data["collect_opened_on"] = "on"
            if evidence.get("cnae"):
                data["collect_cnae"] = "on"
            if evidence.get("canonical_cnpj_confirmed"):
                data["collect_canonical_cnpj_confirmed"] = "on"
            if spec.get("allowed"):
                data["allowed_statuses"] = spec["allowed"]
                data["accepted_statuses"] = spec["accepted"]
                data["failure_statuses"] = spec["failures"]
            post_ok(client, "edital-section-create", [edital.pk, "subcriterios"], data)
            check = RequirementCheck.objects.get(requirement=requirement, code=spec["code"])
            for rule_type, severity, blocks, config in spec.get("validators", []):
                rule_data = {
                    "requirement_check": check.pk,
                    "rule_type": rule_type,
                    "severity": severity,
                    "active": "on",
                }
                if blocks:
                    rule_data["blocks_completion"] = "on"
                if "years" in config:
                    rule_data["years"] = config["years"]
                if "expected_cnae" in config:
                    rule_data["expected_cnae"] = config["expected_cnae"]
                    rule_data["match_mode"] = config["match_mode"]
                post_ok(client, "edital-section-create", [edital.pk, "validacoes"], rule_data)

    post_ok(
        client,
        "edital-edit",
        [edital.pk],
        {
            "name": edital.name,
            "status": "DRAFT",
            "number": edital.number,
            "year": edital.year,
            "description": edital.description,
            "opens_at": "2026-01-01T09:00",
            "closes_at": "2026-12-31T18:00",
            "rules_version": edital.rules_version,
            "minimum_equity_percentage": "10.00",
            "validation_reference_date": reference_date,
            "duplicate_policy": edital.duplicate_policy,
            "duplicate_scope": edital.duplicate_scope,
            "tie_breaker_policy": edital.tie_breaker_policy,
        },
    )
    return edital, program, municipality
