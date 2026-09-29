# Post-audit hardening report — fase 15

Data: 2026-09-28. Estado: **pronto para auditoria independente**, com paridade real FAIL. Os critérios de correção funcional estão verificados localmente; a fonte e decisões abertas impedem afirmar conformidade integral.

## Identidade Git e limites

- Remote verificado: `https://github.com/PUBLIC-DEVS/edital-depad-comunidades.git`.
- Base branch: `feature/initial-edital-platform`.
- Base commit: `8849b2ec5463eb3ec47b1c0ad391d4f1de13cfeb`.
- Main, preservada: `230ec63b49dffe4263ca4c8336216cf84d19aee8`.
- Hardening branch: `feature/initial-edital-platform-hardening`.
- HEAD final de código validado: `724512325e0368c3d49128e6f2542ea048c5de49`.
- HEAD final de publicação: ref `feature/initial-edital-platform-hardening`; hash literal e lista completa após o commit documental estão em `artifacts/private/final-delivery.json` e na entrega final. O commit desse relatório é obtido por `git log -1 --format=%H -- docs/POST_AUDIT_HARDENING_REPORT.md`.
- Working tree inicial limpa; fetch e pull ff-only já atualizados. Nenhum reset, descarte, merge, alteração de main/base ou force push.
- Workbook externo somente leitura; bancos de comparação isolados em artifacts/private. Banco operacional não migrado nem populado nesta tarefa.

## Commits de implementação

```text
d748c2c chore: record post-audit hardening baseline
56ea63b fix: align legacy importer with real workbook schema
66fbe6a fix: align evaluation review and diligence workflow
d08e00c fix: harden ranking eligibility duplicates and snapshots
a654f9b fix: harden authorization and domain integrity
5560fed fix: align financial rules identifiers and framework baseline
f232b20 test: add real legacy workbook golden master
6df1894 fix: preserve unknown historical diligence outcomes
21bd418 test: verify real import idempotency for each process
a505406 fix: scope ranking locks for nullable municipalities
7245123 fix: exercise HTTP test views without disabling production TLS
```

A publicação documental usa `docs: publish post-audit parity and hardening results`. Refinamentos adicionais preservam resultado desconhecido de diligência como LEGACY_UNKNOWN, verificam idempotência por processo e limitam FOR UPDATE à Submission para suportar municípios nulos em PostgreSQL. A migration preserva eventos e acrescenta auditoria, sem inventar decisão jurídica.

## Achados recebidos e confirmados

O teste sintético anterior não demonstrava paridade externa. Coordenadas de DISTRIBUIÇÃO/analistas/revisão/diligência estavam incompatíveis com o arquivo real. Fallbacks fabricavam identificadores e timestamps. PRONASCI não estava numa aba dedicada. Workflow criava revisão universal e colocava o analista como revisor. GET criava Evaluation; decisões admitiam check de outro processo. Diligência voltava universalmente para análise. Ranking incluía não elegíveis/duplicatas, e o boolean de snapshot não protegia edição. Havia permissões globais insuficientes, ausência de duas constraints e fórmula financeira inadequada por grupo. Teste positivo alfanumérico e nomenclatura LTS/documentação precisavam correção. Esses achados foram confirmados por leitura do código e execução independente da fonte.

## Correções e evidência

1. Parsing/normalização/importação/paridade/reporting separados em apps.legacy_import; coordenadas centralizadas. Dois carregamentos do XLSX, caches e fórmulas mantidos, sem salvar a fonte. Somente prefixo ANÁLISE - é analista.
2. SEI E na distribuição/C nas demais; F/G combinados sem now; strict/lenient, issues estruturadas e provenance por run/hash/aba/linha. Nomes recuperados por SEI/CNPJ e IBGE nulo quando não resolvido. Z alimenta PRONASCI. Eventos repetidos não são colapsados.
3. BY recalculado dos checks contextuais, preservando valores brutos e distinções AW/BV; SEI/páginas/CNPJ/validade são evidências. CG é decisão histórica normalizada de revisão; valores desconhecidos não viram pré-habilitado.
4. APTA segue diretamente para elegibilidade; INAPTA cria Review pendente não atribuído. Claim com lock/condição de ownership; checks filtrados pela evaluation; resultados de conclusão validados; reentrada/revisão já concluída rejeitadas.
5. GET workspace sem mutação e POST start somente do analista atribuído. Redistribuição bloqueada depois de iniciar Evaluation; transferência formal permanece requisito futuro.
6. Diligência guarda origem e retorna corretamente quando saneada. Consequência não saneada precisa política expressa; histórico desconhecido tem status/resultado LEGACY_UNKNOWN, datas/prazo/solicitante nulos. Formulários não oferecem resultado histórico para nova operação.
7. Ranking somente elegíveis, com RankingExclusion separado, posições consecutivas por grupo, política ABSOLUTE/ELIGIBLE explícita, classificação persistida/auditada e transições RANKED auditadas. Empates não autorizados bloqueiam geração.
8. Proteção de snapshots/entries/exclusions em save/delete/update/bulk_update/updates por conflito e admin. Captura de nomes/identidade para o snapshot. Snapshots antigos sem metadados de elegibilidade são sinalizados e seu export oficial é bloqueado.
9. Ranking/métricas/history/CSV restritos a admin/coord/consulta no servidor. Testes de IDOR/ownership. Admin operacional somente leitura evita bypass de serviços. AuditEvent existente preservado.
10. Constraints edital+SEI e uma Assignment ACTIVE por Submission. Financeiro Decimal por FEMALE/MALE/NURSING_MOTHER; percentagem no Edital; regras antigas arquivadas sem conversão presumida. Upgrade populado testado.
11. CNPJ numérico/alfanumérico positivo com exemplos oficiais, sem afrouxar validator. Django 5.2.17, Docker/CI/packaging alinhados. Microsoft boundary descrito como scaffold e log de claims reduzido.
12. Golden master externo, fingerprint independente, diffs por processo, métricas separadas, reconciliação e idempotência entre processos. Relatórios antigos e flags excessivos substituídos por fatos demonstrados.

## Migrations criadas (12)

- `apps/accounts/migrations/0002_alter_user_email.py`
- `apps/editais/migrations/0002_programmunicipality_legacy_original_name_and_more.py`
- `apps/editais/migrations/0003_edital_duplicate_scope_edital_tie_breaker_policy.py`
- `apps/editais/migrations/0004_vacancy_type_funding.py`
- `apps/evaluations/migrations/0002_checkresult_legacy_raw_value_and_more.py`
- `apps/institutions/migrations/0002_alter_municipality_ibge_code_and_more.py`
- `apps/legacy_import/migrations/0001_initial.py`
- `apps/ranking/migrations/0003_rankingexclusion_rankingentry_snapshot_data_and_more.py`
- `apps/reviews/migrations/0002_diligence_origin_status_and_more.py`
- `apps/reviews/migrations/0003_unknown_historical_diligence_result.py`
- `apps/submissions/migrations/0003_alter_assignment_assigned_at_and_more.py`
- `apps/submissions/migrations/0004_assignment_unique_active_assignment_submission_and_more.py`

Regras financeiras antigas permanecem em LegacyGroupFundingRule. Os novos tipos precisam configuração explícita ou fórmula histórica reconhecida; não há inferência automática G1 -> tipo de vaga. A migration de resultado desconhecido não restitui um rótulo operacional fictício em seu reverse noop.

## Testes criados ou atualizados

- `tests/conftest.py`
- `tests/integration/test_admin_and_policy_guards.py`
- `tests/integration/test_authorization_hardening.py`
- `tests/integration/test_evaluation_workspace.py`
- `tests/integration/test_funding_migration.py`
- `tests/integration/test_legacy_import_safety.py`
- `tests/integration/test_management_commands.py`
- `tests/integration/test_ranking_flow.py`
- `tests/integration/test_real_legacy_workbook.py`
- `tests/integration/test_reviews_and_diligence.py`
- `tests/integration/test_synthetic_legacy_importer.py`
- `tests/integration/test_workflow_hardening.py`
- `tests/test_bootstrap.py`
- `tests/unit/test_cnpj_official_examples.py`
- `tests/unit/test_domain_models.py`
- `tests/unit/test_evaluation_service.py`
- `tests/unit/test_funding_service.py`
- `tests/unit/test_legacy_normalization.py`
- `tests/unit/test_parity_status.py`
- `tests/unit/test_ranking_hardening.py`

A conclusão é baseada na suíte completa, incluindo o XLSX externo. Ownership concorrente é coberto por tentativa com objeto stale e claim atômico condicionado; não se afirma teste de carga concorrente nem execução local em PostgreSQL.

## Verificação final

A primeira CI executou os requests HTTP do test client com DEBUG=False e SECURE_SSL_REDIRECT=True, recebendo 301 antes das views. A configuração foi corrigida somente no job de testes, e uma regressão confirma o redirecionamento exigido para HTTP e o acesso HTTPS. A proteção de produção não foi removida. A repetição PostgreSQL passou com 191 testes; os dois testes com XLSX externo rodaram localmente.


| Verificação | Resultado verificado |
| --- | --- |
| Baseline pytest | 67 passed |
| Pytest completo com XLSX real | 193 passed, zero falhas/erros/skips; 79.469s |
| Pytest legacy | 5 passed; testes sintéticos |
| Pytest legacy_real | 2 passed; status do comparador FAIL |
| Coverage apps + config | 87.67%; 2845/3245 statements |
| Ruff check / format | PASS / PASS; arquivos Python verificados conforme Ruff |
| Django check | Sem issues |
| makemigrations --check | Sem mudanças pendentes |
| git diff --check | Vazio na comparação com a base e no working diff |
| Migrations em banco isolado | Aplicadas; upgrade com regra financeira antiga preservada testado |
| XLSX | Hash inalterado; nenhum save da fonte |
| CI PostgreSQL 16 | PASS; 191 passed, 2 legacy_real deselected; [run 36510344583](https://github.com/PUBLIC-DEVS/edital-depad-comunidades/actions/runs/36510344583) |


O ambiente .venv em árvore sincronizada apresentou arquivos compressed,dataless e processos bloqueados em read(). A validação foi executada com Python 3.12.8 num ambiente temporário fora do iCloud, bytecode/cache externos e o mesmo projeto instalado em modo editable. Dependências e resultados estão registrados nos artefatos privados. Não se confundiu o bloqueio de leitura local com falha do domínio.

Oito warnings de openpyxl referem-se à extensão de validação não suportada e datas seriais inválidas em células auxiliares. Nenhum deles foi resolvido salvando o workbook; o hash da fonte permaneceu igual.

## Golden master real e divergências restantes

- Status FAIL; 282 processos comparados; 302 ocorrências (297 campos + 3 erros de fonte + 2 métricas), 183 SEIs com alguma diferença de campo.
- Grupos brutos corretos e ranking histórico 172 reproduzido por presença/posição de cada SEI.
- Resultado inicial 180/102 armazenado versus 71/211 calculado; 109 BY literais com checks negativos. O responsável autorizou manter manual como histórico e cálculo como operacional.
- 6 nomes institucionais e 12 municípios diferem do cadastro canônico; UF ausente e variantes de nome continuam rastreáveis. U coincide; um V sem cache diverge de zero calculado.
- Linha sem SEI e dois status desconhecidos impedem strict. APTAS exibidas em MÉTRICAS não se reconciliam por SEI por falta de caches BX.
- Snapshot operacional bloqueado: 130 candidatos após revisões/duplicidades, dois empates envolvendo quatro candidatos. Bloqueio mantido por decisão expressa do responsável.
- Efeitos jurídicos das diligências, resultado jurídico recalculado das revisões e precedência em empates continuam questões abertas. Não se inventaram respostas.

CSV e tabelas de reconciliação: [REAL_LEGACY_PARITY.md](REAL_LEGACY_PARITY.md). Summary agregado: [artifacts/legacy-real-summary.json](../artifacts/legacy-real-summary.json). Evidência dos checks: [final-audit.json](../artifacts/final-audit.json).

Readiness: PR de hardening para auditoria independente, com pendências explícitas; não pronto para emitir ranking oficial ou declarar conformidade integral. CI PostgreSQL do código validado aprovada; isso não resolve as questões de negócio ou a paridade FAIL. O lock do ranking usa of=(self,) para evitar locking de join nullable; referência: [Django select_for_update](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update). Nenhum merge realizado.

## Arquivos alterados

Inventário no fechamento desta fase; pode ser reproduzido com git diff --name-only feature/initial-edital-platform...HEAD.

```text
.github/workflows/ci.yml
.gitignore
Dockerfile
README.md
apps/accounts/adapters/microsoft.py
apps/accounts/migrations/0002_alter_user_email.py
apps/accounts/models.py
apps/accounts/permissions.py
apps/audit/admin_support.py
apps/editais/admin.py
apps/editais/migrations/0002_programmunicipality_legacy_original_name_and_more.py
apps/editais/migrations/0003_edital_duplicate_scope_edital_tie_breaker_policy.py
apps/editais/migrations/0004_vacancy_type_funding.py
apps/editais/models.py
apps/evaluations/admin.py
apps/evaluations/migrations/0002_checkresult_legacy_raw_value_and_more.py
apps/evaluations/models.py
apps/evaluations/services/evaluation.py
apps/evaluations/urls.py
apps/evaluations/views.py
apps/institutions/migrations/0002_alter_municipality_ibge_code_and_more.py
apps/institutions/models.py
apps/legacy_import/__init__.py
apps/legacy_import/finance.py
apps/legacy_import/importer.py
apps/legacy_import/management/__init__.py
apps/legacy_import/management/commands/__init__.py
apps/legacy_import/management/commands/audit_legacy_real.py
apps/legacy_import/migrations/0001_initial.py
apps/legacy_import/migrations/__init__.py
apps/legacy_import/models.py
apps/legacy_import/normalizers.py
apps/legacy_import/parity.py
apps/legacy_import/parser.py
apps/legacy_import/reporting.py
apps/legacy_import/schema.py
apps/ranking/admin.py
apps/ranking/migrations/0003_rankingexclusion_rankingentry_snapshot_data_and_more.py
apps/ranking/models.py
apps/ranking/services/classification.py
apps/ranking/services/ranking.py
apps/ranking/views.py
apps/reporting/views.py
apps/reviews/admin.py
apps/reviews/forms.py
apps/reviews/migrations/0002_diligence_origin_status_and_more.py
apps/reviews/migrations/0003_unknown_historical_diligence_result.py
apps/reviews/models.py
apps/reviews/services.py
apps/reviews/urls.py
apps/reviews/views.py
apps/submissions/admin.py
apps/submissions/management/__init__.py
apps/submissions/management/commands/__init__.py
apps/submissions/management/commands/import_legacy_edital.py
apps/submissions/management/commands/seed_demo.py
apps/submissions/migrations/0003_alter_assignment_assigned_at_and_more.py
apps/submissions/migrations/0004_assignment_unique_active_assignment_submission_and_more.py
apps/submissions/models.py
apps/submissions/services/duplicates.py
apps/submissions/services/funding.py
apps/submissions/services/legacy_generator.py
apps/submissions/services/legacy_importer.py
apps/submissions/services/workflow.py
apps/submissions/views.py
artifacts/final-audit.json
artifacts/legacy-real-summary.json
config/settings.py
docs/FINAL_AUDIT_CHECKLIST.md
docs/FINAL_IMPLEMENTATION_REPORT.md
docs/FINANCIAL_RULES.md
docs/LEGACY_IMPORT_SCHEMA.md
docs/LEGACY_PARITY.md
docs/POST_AUDIT_BASELINE.md
docs/POST_AUDIT_HARDENING_REPORT.md
docs/REAL_LEGACY_PARITY.md
docs/adr/0004-authentication-boundary.md
docs/design-system.md
docs/domain-model.md
docs/legacy-excel-mapping.md
docs/security.md
docs/testing.md
pyproject.toml
templates/base.html
templates/evaluations/not_started.html
templates/ranking/index.html
templates/reviews/detail.html
templates/reviews/diligence_create.html
templates/reviews/diligence_detail.html
tests/conftest.py
tests/integration/test_admin_and_policy_guards.py
tests/integration/test_authorization_hardening.py
tests/integration/test_evaluation_workspace.py
tests/integration/test_funding_migration.py
tests/integration/test_legacy_import_safety.py
tests/integration/test_management_commands.py
tests/integration/test_ranking_flow.py
tests/integration/test_real_legacy_workbook.py
tests/integration/test_reviews_and_diligence.py
tests/integration/test_synthetic_legacy_importer.py
tests/integration/test_workflow_hardening.py
tests/test_bootstrap.py
tests/unit/test_cnpj_official_examples.py
tests/unit/test_domain_models.py
tests/unit/test_evaluation_service.py
tests/unit/test_funding_service.py
tests/unit/test_legacy_normalization.py
tests/unit/test_parity_status.py
tests/unit/test_ranking_hardening.py
```
