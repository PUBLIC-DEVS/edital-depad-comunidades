"""Coordinates of PLANILHA ANÁLISE EDITAL-13; never used by domain services."""

DISTRIBUTION = dict(
    zip(
        [
            "number",
            "has_contract",
            "institution",
            "cnpj",
            "processo_sei",
            "date",
            "time",
            "group",
            "analyst",
            "address",
            "cep",
            "state",
            "municipality",
            "vagas_femininas",
            "vagas_masculinas",
            "vagas_maes_nutrizes",
            "vagas_solicitadas",
            "capacidade_total",
            "phone",
            "email",
            "valor_global",
            "patrimonio_minimo",
        ],
        list("ABCDEFGHIJKLMNOPQRSTUV"),
        strict=True,
    )
)
ANALYST_IDENTITY = {"institution": "A", "cnpj": "B", "processo_sei": "C", "analyst": "D"}
ANALYST_RESULT = {
    "result": "BY",
    "failed": "BZ",
    "review_result": "CA",
    "review_failed": "CB",
    "reviewer": "CC",
}
REVIEW = {
    **ANALYST_IDENTITY,
    "has_contract": "E",
    "notes": "F",
    "diligence": "G",
    "status": "H",
    "failed": "I",
    "reviewer": "J",
    "initial_result": "CE",
    "initial_failed": "CF",
    "result": "CG",
}
DILIGENCE = {
    **ANALYST_IDENTITY,
    "has_contract": "E",
    "notes": "F",
    "reason": "G",
    "status": "H",
    "reviewer": "I",
    "initial_result": "CD",
    "initial_failed": "CE",
    "result": "CF",
}
# Requirement -> real status columns, evidence columns (SEI, pages, CNPJ, validity, equity).
CHECKS = {
    "4.2-III": (["E"], {"sei_number": "F", "pages": "G"}),
    "4.2-IV": (["H"], {"sei_number": "I", "pages": "J"}),
    "4.2-V": (list("KLMNOPQ"), {"sei_number": "R", "pages": "S"}),
    "4.2-VI": (["T"], {"sei_number": "U", "pages": "V"}),
    "4.2-VII": (["W"], {"sei_number": "X", "pages": "Y"}),
    "4.2-VIII": (["Z"], {"sei_number": "AA", "pages": "AB"}),
    "4.2-IX": (["AC"], {"sei_number": "AD", "pages": "AE"}),
    "4.2-X": (["AF", "AG"], {"sei_number": "AH", "pages": "AI", "minimum_equity": "AJ"}),
    "4.2-XI": (
        ["AK"],
        {"document_cnpj": "AL", "valid_until": "AM", "sei_number": "AN", "pages": "AO"},
    ),
    "4.2-XII": (["AP"], {"sei_number": "AQ", "pages": "AR"}),
    "4.2-XIII": (["AS"], {"sei_number": "AT", "pages": "AU"}),
    "4.2-XIV": (["AV", "AW"], {"sei_number": "AX", "pages": "AY"}),
    "4.2-XV": (["AZ"], {"sei_number": "BA", "pages": "BB"}),
    "4.2-XVI": (["BD"], {"document_cnpj": "BC", "sei_number": "BE", "pages": "BF"}),
    "4.2-XVII": (
        ["BG"],
        {"document_cnpj": "BH", "valid_until": "BI", "sei_number": "BJ", "pages": "BK"},
    ),
    "4.2-XVIII": (["BL"], {"sei_number": "BM", "pages": "BN"}),
    "4.2-XIX": (["BO"], {"sei_number": "BP", "pages": "BQ"}),
    "4.2-XX": (["BR"], {"sei_number": "BS", "pages": "BT"}),
    "4.2-XXI": (["BU", "BV"], {"sei_number": "BW", "pages": "BX"}),
}
RANKING = {
    "G1": dict(
        zip(
            ["position", "institution", "cnpj", "processo_sei", "date", "time", "group"],
            list("BCDEFGH"),
            strict=True,
        )
    ),
    "G2": dict(
        zip(
            ["position", "institution", "cnpj", "processo_sei", "date", "time", "group"],
            list("JKLMNOP"),
            strict=True,
        )
    ),
    "G3": dict(
        zip(
            ["position", "institution", "cnpj", "processo_sei", "date", "time", "group"],
            list("RSTUVWX"),
            strict=True,
        )
    ),
}
