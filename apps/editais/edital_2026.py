"""Declarative, Excel-independent starter configuration for the 2026 edital."""

from apps.editais.models import (
    ClassificationPolicy,
    Program,
    Requirement,
    RequirementCheck,
    RequirementValidationRule,
    TargetGroup,
)
from apps.editais.services import EditalConfigurationService

DOCUMENTS_2026 = (
    {
        "code": "ANEXO_I",
        "name": "Anexo I — Requerimento de Participação",
        "section": "Participação",
        "checks": [
            {
                "code": "REQUERIMENTO",
                "name": "Documento atende?",
                "evidence": {
                    "document_cnpj": True,
                    "canonical_cnpj_confirmed": True,
                },
                "validators": [("CNPJ_MATCH_CANONICAL", "CRITICAL", True, {})],
            }
        ],
    },
    {
        "code": "ANEXO_II",
        "name": "Anexo II — Ficha Cadastral da Entidade",
        "section": "Participação",
        "checks": [{"code": "FICHA_CADASTRAL", "name": "Anexo II atende?"}],
    },
    {
        "code": "ANEXO_III",
        "name": "Anexo III — Experiência Prévia da Entidade",
        "section": "Participação",
        "checks": [
            {"code": "EXPERIENCIA", "name": "Anexo III atende?"},
            {
                "code": "COMPROVACAO_AUTODECLARADA",
                "name": "Documentação comprobatória quando experiência for autodeclarada",
                "required": False,
                "allowed": ["ATENDE", "NAO_ATENDE", "NAO_APLICAVEL"],
                "accepted": ["ATENDE", "NAO_APLICAVEL"],
                "failures": ["NAO_ATENDE"],
            },
        ],
    },
    {
        "code": "ESTATUTO",
        "name": "Estatuto",
        "section": "Constituição e governança",
        "checks": [
            ("OBJETIVOS", "a) Objetivos, atividades e finalidades"),
            ("SEM_REMUNERACAO", "b) Não remunera vantagens ou benefícios"),
            ("SEM_FINS_LUCRATIVOS", "c) Entidade privada sem fins lucrativos"),
            (
                "DISSOLUCAO_PATRIMONIO",
                "d) Regra de dissolução e transferência do patrimônio líquido para entidade congênere",
            ),
            (
                "REGRAS_ASSOCIADOS",
                "e) Regras de admissão, demissão, exclusão, direitos e deveres dos associados",
            ),
            ("MANDATO_DIRETORIA", "f) Mandato da diretoria"),
            ("ESCRITURACAO_NBC", "g) Escrituração conforme NBC"),
        ],
    },
    {
        "code": "SICAF",
        "name": "SICAF de VI níveis",
        "section": "Regularidade cadastral",
        "checks": [
            {
                "code": "REGULARIDADE_SICAF",
                "name": "SICAF de VI níveis atende?",
                "evidence": {"document_cnpj": True, "valid_until": True},
                "validators": [
                    ("CNPJ_MATCH_CANONICAL", "CRITICAL", True, {}),
                    (
                        "DATE_NOT_EXPIRED",
                        "CRITICAL",
                        True,
                        {"reference_date": "EDITAL_REFERENCE_DATE"},
                    ),
                ],
            }
        ],
    },
    {
        "code": "ATA_ELEICAO",
        "name": "Ata de eleição",
        "section": "Constituição e governança",
        "checks": [
            {"code": "VIGENCIA_MANDATO", "name": "Data de vigência do mandato da atual diretoria"},
            {"code": "REGISTRO_CARTORIO", "name": "Registro em cartório"},
        ],
    },
    {
        "code": "ENDERECO_ENTIDADE",
        "name": "Comprovante de endereço da entidade",
        "section": "Representação e endereço",
        "checks": [
            {
                "code": "ENDERECO_ACOLHIMENTO",
                "name": "Comprovante de endereço do local de acolhimento",
                "evidence": {"document_cnpj": True},
                "validators": [("CNPJ_MATCH_CANONICAL", "CRITICAL", True, {})],
            }
        ],
    },
    {
        "code": "REPRESENTANTE_LEGAL",
        "name": "Representante legal",
        "section": "Representação e endereço",
        "checks": [
            {
                "code": "IDENTIFICACAO_REPRESENTANTE",
                "name": "CPF / RG / CNH do representante legal",
            },
            {
                "code": "ENDERECO_REPRESENTANTE",
                "name": "Comprovante de endereço do representante legal",
            },
        ],
    },
    {
        "code": "CNPJ_ENTIDADE",
        "name": "Inscrição no CNPJ",
        "section": "Regularidade cadastral",
        "checks": [
            {
                "code": "IDADE_CNAE",
                "name": "No mínimo três anos de atividade e CNAE esperado",
                "evidence": {"opened_on": True, "cnae": True},
                "validators": [
                    (
                        "CNPJ_MINIMUM_AGE",
                        "CRITICAL",
                        True,
                        {"years": 3, "reference_date": "EDITAL_REFERENCE_DATE"},
                    ),
                    (
                        "CNAE_REQUIRED",
                        "WARNING",
                        False,
                        {"expected_cnae": "87.20-4-99", "match_mode": "UNRESOLVED"},
                    ),
                ],
            }
        ],
    },
    {
        "code": "CORPO_BOMBEIROS",
        "name": "Corpo de Bombeiros",
        "section": "Licenças",
        "checks": [
            {
                "code": "ALVARA_BOMBEIROS",
                "name": "Alvará do Corpo de Bombeiros",
                "evidence": {"document_cnpj": True, "valid_until": True},
                "validators": [
                    ("CNPJ_MATCH_CANONICAL", "CRITICAL", True, {}),
                    (
                        "DATE_NOT_EXPIRED",
                        "CRITICAL",
                        True,
                        {"reference_date": "EDITAL_REFERENCE_DATE"},
                    ),
                ],
            }
        ],
    },
    {
        "code": "ALVARA_SANITARIO",
        "name": "Alvará Sanitário",
        "section": "Licenças",
        "checks": [
            {
                "code": "LICENCA_SANITARIA",
                "name": "Alvará Sanitário",
                "evidence": {"document_cnpj": True, "valid_until": True},
                "validators": [
                    ("CNPJ_MATCH_CANONICAL", "CRITICAL", True, {}),
                    (
                        "DATE_NOT_EXPIRED",
                        "CRITICAL",
                        True,
                        {"reference_date": "EDITAL_REFERENCE_DATE"},
                    ),
                ],
            }
        ],
    },
    {
        "code": "ANEXO_IV",
        "name": "Anexo IV — Programa Terapêutico",
        "section": "Projeto e estrutura",
        "checks": [{"code": "PROGRAMA_TERAPEUTICO", "name": "Anexo IV atende?"}],
    },
    {
        "code": "PLANTA_BAIXA",
        "name": "Planta baixa",
        "section": "Projeto e estrutura",
        "checks": [
            {
                "code": "RESPONSAVEL_TECNICO",
                "name": "Assinada por técnico habilitado (engenheiro ou arquiteto)",
                "evidence": {"document_cnpj": True},
                "validators": [("CNPJ_MATCH_CANONICAL", "CRITICAL", True, {})],
            }
        ],
    },
    {
        "code": "RELATORIO_FOTOGRAFICO",
        "name": "Relatório fotográfico",
        "section": "Projeto e estrutura",
        "checks": [
            {
                "code": "FOTOS_UNIDADE",
                "name": "Relatório fotográfico atualizado da unidade de acolhimento",
            }
        ],
    },
)


def configure_edital_2026_base(edital, actor):
    """Create the coordinator's documented 2026 configuration as editable domain records."""
    program = Program.objects.filter(code="PRONASCI").first()
    if program is None:
        program = EditalConfigurationService.save_program(
            Program(code="PRONASCI", name="PRONASCI"), actor
        )

    groups = (
        ("G1", "Gênero Feminino", ["FEMALE", "NURSING_MOTHER"], None),
        ("G2", "PRONASCI", ["MALE"], program),
        ("G3", "Gênero Masculino", ["MALE"], None),
    )
    for order, (code, name, vacancy_types, group_program) in enumerate(groups, 1):
        EditalConfigurationService.save(
            TargetGroup(
                edital=edital,
                code=code,
                name=name,
                order=order,
                vacancy_types=vacancy_types,
                program=group_program,
            ),
            actor,
        )
    EditalConfigurationService.save(
        ClassificationPolicy(
            edital=edital,
            policy_type="VACANCY_TARGET_POLICY_V2_MIXED_FIRST",
            mixed_group_code="G1",
        ),
        actor,
    )
    for requirement_order, document in enumerate(DOCUMENTS_2026, 1):
        requirement = EditalConfigurationService.save(
            Requirement(
                edital=edital,
                code=document["code"],
                name=document["name"],
                presentation_section=document["section"],
                order=requirement_order,
                mandatory=True,
                requires_checks=True,
                failure_behavior="SEND_TO_REVIEW",
            ),
            actor,
        )
        for check_order, spec in enumerate(document["checks"], 1):
            if isinstance(spec, tuple):
                spec = {"code": spec[0], "name": spec[1]}
            evidence = spec.get("evidence", {})
            check = EditalConfigurationService.save(
                RequirementCheck(
                    requirement=requirement,
                    code=spec["code"],
                    name=spec["name"],
                    order=check_order,
                    required=spec.get("required", True),
                    allowed_statuses=spec.get("allowed", ["ATENDE", "NAO_ATENDE"]),
                    accepted_statuses=spec.get("accepted", ["ATENDE"]),
                    failure_statuses=spec.get("failures", ["NAO_ATENDE"]),
                    collect_sei_number=True,
                    collect_pages=True,
                    collect_notes=True,
                    collect_document_cnpj=evidence.get("document_cnpj", False),
                    collect_valid_until=evidence.get("valid_until", False),
                    collect_opened_on=evidence.get("opened_on", False),
                    collect_cnae=evidence.get("cnae", False),
                    collect_canonical_cnpj_confirmed=evidence.get(
                        "canonical_cnpj_confirmed", False
                    ),
                ),
                actor,
            )
            for rule_type, severity, blocks, config in spec.get("validators", []):
                EditalConfigurationService.save(
                    RequirementValidationRule(
                        requirement_check=check,
                        rule_type=rule_type,
                        severity=severity,
                        blocks_completion=blocks,
                        config=config,
                    ),
                    actor,
                )
    return program


def configuration_fingerprint():
    return {
        "requirements": len(DOCUMENTS_2026),
        "checks": sum(len(document["checks"]) for document in DOCUMENTS_2026),
    }
