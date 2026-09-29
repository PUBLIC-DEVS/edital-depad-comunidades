# Fase 17.1 — Audit remediation

## Resultado e identidade

**READY_FOR_PR_WITH_NON_BLOCKING_FINDINGS**, sujeito à auditoria curta independente. Não é aprovação jurídica nem prontidão para produção.

- Branch: `feature/edital-2026-audit-remediation`.
- Base auditada: `dcbe499408ab47a662006172e3cf3dfa182714d6` (`feature/edital-2026-base-adaptation`).
- Base original Fase 17: `fc185fee64df818cc28a19d010f66566dd4b83ec`.
- Main preservada: `230ec63b49dffe4263ca4c8336216cf84d19aee8`.
- HEAD do código/testes validado: `4154f448b42814c70050ebd1358a919f1aa000b9`.
- HEAD de entrega: o commit final que contém este relatório; consultar `git rev-parse feature/edital-2026-audit-remediation` (não é possível gravar o hash de um commit dentro do próprio conteúdo).
- Estado inicial limpo; fetch/prune, switch e pull ff-only conferidos antes da branch nova.
- Nenhum merge ou PR criado. Push limitado à branch de remediação.

## Escopo e achados

| Finding | Original severity | Status | Files | Tests | Notes |
|---|---|---|---|---|---|
| F17-01 | BLOQUEADOR | FIXED | `apps/editais/edital_2026.py`; testes de configuração/lifecycle | `test_phase17_1_anexo_iii.py`; lifecycle HTTP | Obrigatório quando aplicável, N/A permitido e aceito; falha INAPTA, pendência EM_ANALISE. Teste incorreto substituído. |
| F17-02 | ALTO | FIXED | `services/identity.py`; forms/views e detalhe do processo | `test_phase17_1_identity_correction.py` | Admin/Coord, confirmação e motivo, reassociação transacional só da candidatura, confirmação renovada, documentos preservados e revalidação auditada. |
| F17-03 | MÉDIO | FIXED | `services/intake.py`; views manual/CSV | `test_phase17_1_intake_restriction.py`; importação transacional existente | Pipeline único para dados validados, persistência, classificação, triagem, warnings e auditoria. |
| F17-04 | ALTO | FIXED | `services/eligibility.py`, `workflow.py`, views/URL/detalhe | `test_phase17_1_intake_restriction.py` | Desativação não reabre. Liberação formal só de bloqueio pré-análise comprovado, sem restrições restantes; retorno RECEIVED sem assignment. INELIGIBLE não recebe assignment. |
| F17-05 | ALTO | FIXED | `validation_dependencies.py`; models/forms de regras | `test_phase17_1_validator_dependencies.py` | Registry central de evidências necessárias; Model/Form clean e publicação rejeitam incompatibilidade. Regras inativas não bloqueiam. |
| F17-06 | MÉDIO | FIXED | `administration/forms.py`, views, `institutions/postal.py`, intake form | `test_phase17_1_csv_postal.py` | Campo existente, CEP com/sem hífen normalizado; alteração auditada e edição protegida. |
| F17-07 | MÉDIO | DEFERRED | Workspace existente preservado | Não criado teste de comportamento novo | DEFERRED_TO_HOMOLOGATION. Confirmar compartilhamento de evidência por bloco com a coordenação; nenhum model Evidence/refactor. |
| F17-08 | MÉDIO | FIXED | `apps/csv_utils.py`; exports ranking/reporting | `test_phase17_1_csv_postal.py` | Todas as células dos exports operacionais passam por helper; fórmulas com espaços/controles iniciais neutralizadas; números reais preservados. |
| F17-09 | MÉDIO | FIXED | `services/validation.py` | `test_phase17_1_preview_financial.py` | Ausência de valor global só gera anomaly quando financeiro é requerido. |
| F17-10 | BAIXO | FIXED | `editais/selectors.py`, preview view/template, assessment | `test_phase17_1_preview_financial.py` | Mesmo selector de checks ativos; fallback direto quando só há inativos; GET sem writes. |
| F17-11 | MÉDIO | DEFERRED | Workspace/validator evaluator preservados | Nenhum contrato de queries criado | DEFERRED_PRE_HOMOLOGATION. Otimização de consultas não é acceptance desta rodada. |

Caminhos completos dos services mencionados: `apps/submissions/services/`. Novas regressões estão em `tests/regression/`.

## Semântica do Anexo III

Com todos os demais checks ATENDE:

| Comprovação autodeclarada | Resultado | Consequência |
|---|---|---|
| ATENDE | APTA | Satisfaz. |
| NÃO ATENDE | INAPTA | ANEXO_III listado e CheckResult impeditivo identificado; HTTP conclui e cria Review sem reviewer. |
| NÃO APLICÁVEL | APTA | Satisfaz porque a configuração permite/aceita N/A. |
| EM_BRANCO | EM_ANALISE | Um item pendente; conclusão rejeitada. |

Nenhuma alteração genérica foi necessária no cálculo para essa semântica. Assessment só recebeu o selector compartilhado da prévia. Não existe linguagem de condições.

Configurações previamente publicadas não são alteradas silenciosamente. Uma edição antiga deve ser clonada/versionada pelo CRUD; em rascunho, marque comprovação obrigatória e mantenha N/A permitido/aceito antes de publicar.

## Recuperação operacional e autorização

A fonte canônica continua `submission.institution.cnpj`, sem campo duplicado em Submission. Correção reassocia a candidatura a uma Institution existente/criada; não modifica o CNPJ da instituição compartilhada. Preserva Evaluation e CheckResults, inclusive CNPJs documentais, decisões e notas. A confirmação canônica antiga é invalidada com AuditEvent por campo; o analista confirma novamente. A auditoria da operação registra old/new, motivo, IDs de instituições e candidaturas duplicadas, além dos IDs/status das regras reavaliadas.

Operação autorizada antes de Evaluation ou durante DRAFT/UNDER_ANALYSIS. Não altera decisões concluídas, ranking ou processo encerrado. Novo CNPJ com restrição ativa durante análise provoca rejeição transacional explícita, preservando a identidade anterior; a operação não é override jurídico de elegibilidade. Tratar a fonte formalmente antes de repetir a recuperação. Esses limites são deliberados para não invalidar decisões/snapshots silenciosamente.

Liberação de restrição exige evidência de transição por restrição antes de análise, ausência de Evaluation e de Assignment ACTIVE, ausência de todas as fontes ativas, justificativa e confirmação HTTP. Não libera INELIGIBLE decorrente de decisão documental. Desativar fonte não muda processos históricos. A operação retorna RECEIVED; a próxima atribuição é confirmada separadamente.

| Papel | Corrigir CNPJ | Liberar bloqueio |
|---|---|---|
| ADMINISTRADOR | Sim | Sim |
| COORDENADOR | Sim | Sim |
| DISTRIBUIDOR | Não | Não |
| ANALISTA | Não | Não |
| REVISOR | Não | Não |
| CONSULTA | Não | Não |

Services usam atomic/locks da Submission; recuperação de identidade também trava Evaluation. Novas URLs são POST-only, com CSRF. GET não corrige nem libera.

## CSV, CEP e configuração

`sanitize_csv_cell` prefixa apóstrofo se a string, ignorando espaços Unicode/controles ASCII/DEL/BOM iniciais para detecção, começa com `=`, `+`, `-` ou `@`. O conteúdo original é preservado após o apóstrofo. Valores numéricos reais, None e texto comum não são convertidos. SafeCsvWriter é aplicado a ranking e métricas, os exports operacionais existentes. O CSV de intake permanece transacional por arquivo; entradas não são alteradas como se fossem exports. Diagnósticos privados do módulo legado não foram modificados, conforme a fronteira de escopo.

CEP usa Institution.postal_code existente. Forms aceitam oito dígitos com/sem hífen e normalizam para cinco-três; edição auditada pelo mecanismo existente.

Dependencies de validator: CNPJ_MATCH_CANONICAL → document_cnpj; DATE_NOT_EXPIRED → valid_until; CNPJ_MINIMUM_AGE → opened_on; CNAE_REQUIRED → cnae. Configuração incompatível não publica; datas e parâmetros jurídicos não recebem defaults novos.

## Migrations e fronteiras

Nenhuma migration nova: não houve mudança de campos/constraints/tabelas. Migration check sem pendências. Nenhum arquivo do legacy_import, workbook, integração Microsoft, dependência ou CI alterado. Django permanece 5.2 LTS (patch do ambiente: 5.2.17).

APTA/INAPTA routing, review claim/ownership/completude/coerência, diligência por origem, GET workspace seguro, ranking/exclusões/imutabilidade, AuditEvent append-only e por campo, métricas separadas e RBAC foram exercidos pela suíte completa. Nenhuma decisão jurídica aberta foi resolvida.

## Commits

```text
8d72ee2 chore: record phase 17.1 remediation baseline
6c161c2 fix: correct conditional requirement assessment
7d4dfd4 fix: add audited submission identity recovery
9a2f18a fix: unify intake screening and restriction recovery
00318c6 fix: validate requirement rules against collected evidence
b25ca89 fix: complete institution and export safety handling
9f56f79 fix: align optional financial checks and analyst preview
4154f44 test: add phase 17.1 audit recovery regressions
```

O commit final `docs: document phase 17.1 remediation` acrescenta este relatório e corrige README/mapping/adaptation/open decisions.

## Validação

Baseline: **229 passed, 2 skipped**; sem legado **217 passed**; synthetic legacy **7 passed**. Baseline completo em [PHASE_17_1_BASELINE.md](PHASE_17_1_BASELINE.md).

Ambiente isolado: Python 3.12.8, Django 5.2.17, SQLite temporário, bytecode e coverage fora do repositório. Sem alteração do banco local de desenvolvimento. Suíte final: **295 passed, 2 skipped**, ou **66 regressões novas**; lifecycle 2026 atualizado para falha aplicável do Anexo III.

Coverage: **84,28%** (4241/5032 statements; 791 faltantes), exibido como 84%. Identity 94%; eligibility 88%; intake 92%; csv helper 100%; selector 100%; assessment 100%. Cobertura anterior reproduzida: 83%.

| Comando/verificação | Exit code | Tempo (s) | Resultado |
|---|---:|---:|---|
| django | 0 | 0.2 | 0 issues |
| migrations | 0 | 0.21 | No changes detected |
| pytest | 0 | 20.93 | 295 passed, 2 skipped |
| no_legacy | 0 | 8.75 | 283 passed |
| legacy | 0 | 13.35 | 7 passed |
| coverage | 0 | 54.43 | 295 passed, 2 skipped; 84,28% |
| ruff | 0 | 0.07 | All checks passed |
| format | 0 | 0.02 | 184 files already formatted |
| diff | 0 | 0.02 | Saída vazia |
| base_diff | 0 | 0.04 | Saída vazia |
| pytest -k "anexo_iii or autodeclarada" | 0 | 2.43 | 4 passed, 293 deselected |
| pytest -k "restriction" | 0 | 2.13 | 13 passed, 284 deselected |
| pytest -k "identity or cnpj" | 0 | 1.97 | 34 passed, 263 deselected |
| pytest -k "validator" | 0 | 1.73 | 9 passed, 288 deselected |
| pytest -k "csv" | 0 | 2.11 | 37 passed, 260 deselected |
| pytest -k "preview" | 0 | 1.98 | 8 passed, 289 deselected |
| pytest -k "financial" | 0 | 4.85 | 10 passed, 287 deselected |

Skips: exclusivamente testes históricos reais com LEGACY_XLSX_PATH ausente: **NOT_RUN**, sem paridade PASS. Testes 2026 não abrem XLSX e o lifecycle é **HTTP integration lifecycle**: usuários/bootstrap via ORM, operações via Client/views/forms, sem navegador real.

Logs e JSON de cobertura completos fora do Git: `/private/tmp/phase17-1-validation/`. CI desta branch será identificada no GitHub após o push; os resultados acima são locais, não presumem execução remota.

## Decisões abertas e riscos restantes

Continuam abertas: data oficial de referência; CNAE principal/único/qualquer; política definitiva de duplicidade; confirmação de nutrizes G1; fonte oficial PRONASCI; desempate absoluto. Nenhum default jurídico novo.

F17-07/F17-11 adiados; homologação de UX e navegador, dados oficiais e concorrência em PostgreSQL continuam necessárias. Esta rodada validou SQLite local; não declara teste concorrente de produção. Integração Microsoft segue boundary/scaffold. Sem browser dependency, sem tentativa de obter legacy real PASS.

Main e branch auditada permanecem nos SHAs acima. Não houve merge; PR não é aberto automaticamente. A branch é entregue para auditoria curta independente.
