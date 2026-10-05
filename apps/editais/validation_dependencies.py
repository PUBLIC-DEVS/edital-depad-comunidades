"""Evidence dependencies shared by rule editing and publication validation."""

VALIDATOR_REQUIREMENTS = {
    "CNPJ_MATCH_CANONICAL": {"collect_document_cnpj": "CNPJ do documento"},
    "DATE_NOT_EXPIRED": {"collect_valid_until": "Validade"},
    "CNPJ_MINIMUM_AGE": {"collect_opened_on": "Data de abertura do CNPJ"},
    "CNAE_REQUIRED": {"collect_cnae": "CNAE"},
}


def missing_evidence_messages(rule):
    if not rule.active or not rule.requirement_check_id:
        return []
    return [
        f"Validação '{rule.get_rule_type_display()}' exige que o subcritério colete o campo '{label}'."
        for flag, label in VALIDATOR_REQUIREMENTS.get(rule.rule_type, {}).items()
        if not getattr(rule.requirement_check, flag)
    ]
