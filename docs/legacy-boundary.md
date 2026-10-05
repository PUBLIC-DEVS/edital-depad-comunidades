# Fronteira do legado

`apps.legacy_import` é uma fronteira opcional para migração, inspeção da planilha histórica e testes de regressão/paridade. O importador de 2025 e o workbook não são configuração runtime do produto.

Criar e configurar um edital novo usa os models/serviços de `apps.editais`, `apps.submissions`, `apps.evaluations`, `apps.reviews`, `apps.ranking` e suas telas Django. O formulário do analista lê `Requirement`, `RequirementCheck`, `EvidenceConfiguration` e `RequirementValidationRule` do edital publicado. Classificação lê `TargetGroup`, `ProgramMunicipality` e `ClassificationPolicy`. Nenhum desses serviços operacionais importa `legacy_import`, coordenadas ou nomes de abas de Excel.

`ENABLE_LEGACY_IMPORT=false` remove o app legado da inicialização Django. O lifecycle do Edital 2026 é validado separadamente sem abrir um XLSX.
