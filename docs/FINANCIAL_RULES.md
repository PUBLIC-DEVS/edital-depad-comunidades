# Financial rules

Operational FundingRule is keyed by edital and vacancy type: FEMALE, MALE or NURSING_MOTHER. Duration belongs to each rule; the minimum equity percentage belongs to the edital. Missing types raise an error instead of falling back to a group. Values use Decimal and ROUND_HALF_UP to cents.

The inspected workbook's U formula uses 1172.23 per month for female/male vacancies and 1527.37 for nursing mothers, over 12 months. V requires 10% of U. These are historical parameters, not hardcoded universal application rules. Real parity configures those values explicitly in an isolated development database and compares every process to U/V cached values.

Migration 0004 renames the old group-based table to LegacyGroupFundingRule and creates the vacancy-type table. Old configurations remain intact for audit; they are not automatically converted because G1 does not identify a single vacancy type. Configure new rules before using the financial service in an existing environment.

Framework verification uses Django 5.2 LTS; the supported patch verified for this task is 5.2.17. See [Django supported versions](https://www.djangoproject.com/download/).

CNPJ verification retains the RFB ASCII-minus-48 modulo-11 algorithm. Positive independent examples include `12.ABC.345/01DE-35` from the [RFB checksum manual](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf), and `00.000.000/E08G-12` from the [first official registration](https://www.gov.br/fazenda/pt-br/assuntos/noticias/2026/julho/receita-federal-gera-o-primeiro-cnpj-em-formato-alfanumerico). The validator was not relaxed to make those examples pass.
