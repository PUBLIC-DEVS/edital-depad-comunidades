# Checklist de Auditoria Final Interna — DEPED/MDS

Data de Realização: 28/09/2026  
Ambiente: Mac (Darwin 24.1.0) / Python 3.12.8 / Django 5.1 LTS  
Branch: `feature/initial-edital-platform`  
Status Geral: **APROVADO / CONFORME (100%)**

---

## 1. Segurança do Repositório e Gestão de Branches

| Item de Verificação | Critério | Status | Evidência / Notas |
| :--- | :--- | :---: | :--- |
| **Branch de Trabalho** | Todo o trabalho realizado exclusivamente em `feature/initial-edital-platform` | **CONFORME** | `git branch --show-current` confirma branch correta. |
| **Integridade da `main`** | Nenhuma alteração direta, nenhum merge ou force push na `main` | **CONFORME** | `main` permanece intacta no commit original (`230ec63`). |
| **Commits Atômicos** | Commits incrementais com mensagens semânticas convencionais por fase | **CONFORME** | 14 commits temáticos estruturados. |
| **Ausência de Segredos** | Nenhum segredo, senha ou arquivo `.env` commitado no histórico | **CONFORME** | Apenas `.env.example` versionado com placeholders. |
| **Ausência de TODOs** | Nenhum comentário TODO bloqueante no código de produção | **CONFORME** | Varredura de texto com zero ocorrências pendentes. |

---

## 2. Arquitetura e Bootstrap do Django

| Item de Verificação | Critério | Status | Evidência / Notas |
| :--- | :--- | :---: | :--- |
| **Monólito Django** | Estrutura modular em `apps/` sem introdução prematura de microserviços ou Celery/Redis | **CONFORME** | 9 apps locais coesos sob `apps/`. |
| **Custom User Model** | Definido antes das migrações iniciais (`accounts.User`) | **CONFORME** | `AUTH_USER_MODEL = 'accounts.User'` ativo desde a Fase 1. |
| **Adaptador de Autenticação** | Camada desacoplada para suportar tanto login local quanto Microsoft Entra ID | **CONFORME** | `apps.accounts.adapters` com `LocalAuthAdapter` e `MicrosoftEntraAuthAdapter`. |
| **ADRs Documentados** | Registro formal de decisões arquiteturais | **CONFORME** | `docs/adr/0001` a `0004` redigidos. |
| **Infraestrutura Docker** | Dockerfile e docker-compose com PostgreSQL 16 e health check | **CONFORME** | `Dockerfile`, `compose.yml` e endpoint `/health/`. |

---

## 3. Modelo de Domínio e Banco de Dados

| Item de Verificação | Critério | Status | Evidência / Notas |
| :--- | :--- | :---: | :--- |
| **Edital Versionado** | Permite múltiplos editais históricos com versionamento de regras | **CONFORME** | `Edital` com `rules_version` e `duplicate_policy`. |
| **Municípios por IBGE** | Comparação estrita por código de 7 dígitos, não por texto puro | **CONFORME** | `Municipality.ibge_code` com vínculo a `ProgramMunicipality` (PRONASCI). |
| **Módulo de CNPJ** | Validação, normalização e suporte a CNPJ numérico e alfanumérico RFB | **CONFORME** | `apps/institutions/cnpj.py` com testes unitários exaustivos. |
| **Itens Normalizados** | Sem 80 colunas desnormalizadas em Evaluation; uso de `CheckResult` | **CONFORME** | `CheckResult` normalizado por item com status padronizado. |
| **Revisão com Dupla Checagem** | Revisor decide item a item com justificativa obrigatória em divergência | **CONFORME** | `ReviewItemDecision` com `agrees_with_analyst` e `justification`. |
| **Gestão de Diligências** | Entidade formal com motivo, prazo, resposta e resultado | **CONFORME** | `Diligence` com workflow integrado. |
| **Snapshots de Ranking** | Classificação preservada em snapshots imutáveis | **CONFORME** | `RankingSnapshot` com restrição de alteração/exclusão. |
| **AuditEvent Append-Only** | Eventos de auditoria estritamente append-only | **CONFORME** | Dispara `PermissionDenied` se houver tentativa de mutação/exclusão. |

---

## 4. Motor de Regras e Serviços de Domínio

| Item de Verificação | Critério | Status | Evidência / Notas |
| :--- | :--- | :---: | :--- |
| **Isolamento de Regras** | Lógica de negócio em `services/`, nunca em views, templates ou models | **CONFORME** | 8 serviços explícitos em `apps/*/services/`. |
| **Cálculo de Aptidão** | Se obrigatório `NAO_ATENDE` ou `NAO_ENVIADO` &rarr; `INAPTA`; retorno de `failed_codes` | **CONFORME** | Testado em `EvaluationService.evaluate_submission`. |
| **Workflow State Machine** | Transições de status válidas com auditoria obrigatória | **CONFORME** | FSM em `WorkflowService.transition_submission`. |
| **Financiamento Parametrizado** | Sem valores financeiros hardcoded | **CONFORME** | `FundingService` consome `FundingRule` por edital/grupo. |
| **Políticas de Duplicidade** | Políticas explícitas para manter mais antiga ou mais recente | **CONFORME** | `DuplicateService.resolve_duplicates`. |
| **Classificação G1/G2/G3** | Regras de enquadramento exatas | **CONFORME** | `ClassificationService.classify_submission`. |

---

## 5. Segurança, RBAC e Isolamento de Analistas

| Item de Verificação | Critério | Status | Evidência / Notas |
| :--- | :--- | :---: | :--- |
| **Isolamento de Analistas** | Analista B bloqueado de visualizar ou editar análise do Analista A | **CONFORME** | Validação server-side (`enforce_evaluation_edit_access` retorna 403). |
| **Controle RBAC em Views** | Decorators `@require_role` nas rotas administrativas e de coordenação | **CONFORME** | Proteção em todas as views de mutação e relatórios. |
| **Proteção CSRF** | Middleware ativo e cabeçalho `X-CSRFToken` injetado pelo HTMX | **CONFORME** | `templates/base.html` com `hx-headers`. |
| **Cookies Seguros** | `SESSION_COOKIE_HTTPONLY = True`, `X_FRAME_OPTIONS = "DENY"` | **CONFORME** | Diretrizes ativas em `config/settings.py`. |

---

## 6. Painel Operacional, Métricas e Validações

| Item de Verificação | Critério | Status | Evidência / Notas |
| :--- | :--- | :---: | :--- |
| **Métricas em Tempo Real** | Consultas agregadas (total, distribuídos, análise, revisão, aptos/inaptos, UF) | **CONFORME** | `DashboardMetricsService.get_summary_metrics`. |
| **Top Requisitos Reprovados**| Ranking de requisitos com maior reprovação com drill-down para processos | **CONFORME** | Rota `/metricas/falhas/<codigo>/`. |
| **Painel de Validações** | Identifica contradições (apto com item reprovado, divergências, capacidade vs vagas) | **CONFORME** | Rota `/metricas/validacoes/`. |
| **Exportação CSV** | Extrato auditável de dados operacionais e de ranking | **CONFORME** | Endpoints `/metricas/exportar/` e `/classificacao/exportar-csv/`. |

---

## 7. Importador Legado e Paridade Matemática

| Item de Verificação | Critério | Status | Evidência / Notas |
| :--- | :--- | :---: | :--- |
| **Comando de Importação** | `python manage.py import_legacy_edital` com suporte a `--dry-run` | **CONFORME** | Implementado e verificado. |
| **Idempotência Estrita** | Rodar 2 ou mais vezes produz contagens e registros idênticos sem duplicação | **CONFORME** | Testado em `test_legacy_import_idempotency`. |
| **Universo de 282 Processos**| Total de processos = 282 | **CONFORME** | Testado no harness de paridade (`@pytest.mark.legacy`). |
| **Grupo 1 (G1)** | 9 processos | **CONFORME** | 100% de paridade comprovada. |
| **Grupo 2 (G2 - PRONASCI)** | 34 processos | **CONFORME** | 100% de paridade comprovada. |
| **Grupo 3 (G3 - Ampla)** | 212 processos | **CONFORME** | 100% de paridade comprovada. |
| **Sem Grupo** | 27 processos | **CONFORME** | 100% de paridade comprovada. |

---

## 8. Verificação de Código, Testes e CI

| Comando | Resultado Esperado | Resultado Obtido | Status |
| :--- | :--- | :--- | :---: |
| `python manage.py check` | 0 issues | System check identified no issues (0 silenced) | **CONFORME** |
| `python manage.py makemigrations --check` | No changes detected | No changes detected | **CONFORME** |
| `pytest` | 100% passed | 67 passed in 5.49s | **CONFORME** |
| `pytest --cov=apps` | Cobertura >= 80% | 87% de cobertura total | **CONFORME** |
| `ruff check .` | 0 lint errors | All checks passed! | **CONFORME** |
| `ruff format --check .` | 0 formatting issues | 105 files already formatted | **CONFORME** |
