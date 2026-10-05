# Plano de Implementação: Sistema de Gestão e Análise de Edital (edital-depad-comunidades)

## 1. Objetivo do Sistema

O objetivo deste sistema é substituir um fluxo complexo anteriormente operado em Excel Online por uma plataforma web moderna, relacional, segura e auditável baseada em Django, garantindo integridade operacional para a gestão de editais da DEPED/MDS.

A transição converte:
- **Abas do Excel** → Filas de trabalho, visões segregadas e fluxos orientados a papéis.
- **Fórmulas de planilha** → Regras de domínio explícitas, determinísticas e cobertas por testes unitários e de integração.
- **Células não tipadas** → Modelos relacionais com validação forte, integridade referencial e trilha de auditoria completa (*append-only*).
- **Conferências manuais** → Validações automáticas de inconsistências, duplicidades e filas de exceção proativas.

A plataforma é concebida para permitir auditoria posterior de paridade estrita contra a planilha Excel histórica original (Golden Master).

---

## 2. Arquitetura Escolhida

A arquitetura adota um **Monólito Django Modular** (*clean/service layer pattern*), priorizando manutenibilidade, simplicidade operacional e robustez:

- **Backend / Framework:** Python 3.12+ com Django LTS.
- **Banco de Dados:** PostgreSQL (com suporte de desenvolvimento/fallback SQLite quando configurado localmente).
- **Interface / Frontend:** Django Templates + Tailwind CSS + HTMX (para interatividade reativa em componentes sem sobrecarga de SPA) + Alpine.js mínimo (apenas para comportamento de tela puramente declarativo como toggles/modais).
- **Camada de Serviços de Domínio:** A lógica de negócio, transições de workflow, avaliação documental, cálculo de financiamento e ordenação/ranking habitam em `services/` explícitos, isolados de views, models e templates.
- **Segregação de Acesso (RBAC):** Controle de acesso estrito com papéis (Administrador, Coordenador, Distribuidor, Analista, Revisor, Consulta). Regras de isolamento (ex.: Analista A não acessa processos de Analista B) são aplicadas *server-side* tanto em consultas (GET) quanto em mutações (POST/PUT/DELETE).
- **Camada de Adaptação de Autenticação:** Interface clara de autenticação institucional, permitindo login local em desenvolvimento e acomodando futura integração com Microsoft / Entra ID / SharePoint sem acoplamento do domínio.
- **Auditoria Append-Only:** Registro sistemático de eventos de auditoria com rastreabilidade de autor, timestamp, entidade, ação e diff de valores.

---

## 3. Fases de Execução

1. **Fase 0 — Inspeção, Segurança e Criação da Branch:** Estado do repositório verificado, branch de trabalho isolada criada, plano documentado.
2. **Fase 1 — Arquitetura e Bootstrap do Django:** Configuração base do monólito, PostgreSQL, Custom User Model (`accounts.User`), linters (ruff), pytest, Docker/docker-compose, health check e ADRs.
3. **Fase 2 — Modelo de Domínio:** Modelagem relacional completa (Edital, Municipality, ProgramMunicipality, Institution com módulo dedicado de CNPJ, Submission, Assignment, FundingRule, Requirement, RequirementCheck, CheckResult, Evaluation, Review, ReviewItemDecision, Diligence, RankingSnapshot, RankingEntry, AuditEvent).
4. **Fase 3 — Motor de Regras e Workflow:** `EvaluationService`, `WorkflowService` (máquina de estados finita com transições auditadas), `FundingService`, `DuplicatePolicy`.
5. **Fase 4 — Autorização e Segregação de Dados:** Implementação de RBAC, selectors/policies de permissão, isolamento estrito de analistas e adapter de autenticação.
6. **Fase 5 — Distribuição e Gestão de Processos:** Telas de listagem, busca, filtros, atribuição individual e em lote, sugestão de balanceamento de carga, detecção de anomalias/duplicidades.
7. **Fase 6 — Interface de Análise Documental:** Área "Minhas Análises", layout vertical ergonômico, formulário de checagem documental com salvamento em rascunho, validação por serviço e acessibilidade.
8. **Fase 7 — Revisão e Diligência:** Fila de revisão documental, confirmação/divergência item a item com justificativa obrigatória, subfluxo de abertura e resposta de diligências.
9. **Fase 8 — Classificação, Grupos e Ranking:** `ClassificationService` e `RankingService` determinísticos (G1, G2 via IBGE/PRONASCI, G3, sem grupo), ordenação, snapshots de ranking imutáveis.
10. **Fase 9 — Dashboard, Métricas e Exceções:** Métricas operacionais em tempo real derivadas de consultas do banco, drill-down por falhas de requisitos e tela de anomalias.
11. **Fase 10 — Importador do Excel Legado e Golden Master:** Comando `import_legacy_edital`, preservação de proveniência, warnings estruturados, documentação de mapeamento e harness de paridade com dados de referência conhecidos.
12. **Fase 11 — Design System e Refinamento de UX:** Sistema de design coeso em Tailwind CSS, navegação baseada em papéis, estados visuais e componentes acessíveis.
13. **Fase 12 — Testes, CI, Segurança e Qualidade:** Testes unitários, de serviços, segurança, workflow e integração; pipeline de CI (GitHub Actions); revisão de vulnerabilidades e configurações de produção.
14. **Fase 13 — Documentação Operacional:** Manual completo no `README.md`, comando `seed_demo`, guias de integração e operação.
15. **Fase 14 — Auditoria Interna Final:** Relatório final detalhado (`docs/FINAL_IMPLEMENTATION_REPORT.md`), checklist de validação (`docs/FINAL_AUDIT_CHECKLIST.md`) e resumo JSON (`artifacts/final-audit.json`).

---

## 4. Decisões Conhecidas

- **Decisão 1 (Custom User Model):** Implementação imediata de `accounts.User` antes de qualquer migração, garantindo compatibilidade futura com e-mail institucional e identificadores corporativos.
- **Decisão 2 (Isolamento de Analistas no Servidor):** O isolamento de processos por analista é garantido no QuerySet e no `dispatch` das views, retornando HTTP 403 / 404 para acessos cruzados não autorizados, bloqueando IDOR.
- **Decisão 3 (Tratamento de CNPJ):** Módulo especializado `apps.institutions.cnpj` que aceita CNPJ numérico de 14 dígitos (com formatação e dígitos verificadores) e suporta a futura especificação de CNPJ alfanumérico da Receita Federal.
- **Decisão 4 (Normalização de Requisitos):** Checagens não utilizam 80 colunas flat em uma tabela, mas entidades normalizadas `RequirementCheck` e `CheckResult` vinculadas à `Evaluation`.
- **Decisão 5 (Snapshots de Ranking Imutáveis):** O ranking não é uma coluna mutável; é gerado como `RankingSnapshot` com suas respectivas `RankingEntry`, permitindo comparação histórica e publicação auditada.
- **Decisão 6 (Vínculo PRONASCI por Código IBGE):** Vínculo de municípios ao PRONASCI por código IBGE padronizado de 7 dígitos, eliminando divergências por acentuação, grafia ou casing.

---

## 5. Questões de Negócio Ainda Ambíguas

1. **Política de Duplicidade no Ranking:** A planilha histórica aparentemente adotava `KEEP_EARLIEST_SUBMISSION` (manter a submissão com timestamp mais antigo). Entretanto, existem editais onde a submissão mais recente retifica a anterior (`KEEP_LATEST_SUBMISSION`), ou onde a duplicidade depende de estar apta.
   - *Solução adotada:* Implementar `DuplicatePolicy` configurável por Edital (padrão histórico: `KEEP_EARLIEST_SUBMISSION`), permitindo alternância documentada.
2. **Critério de Desempate entre Submissões no Mesmo Minuto:** Quando duas submissões elegíveis do mesmo grupo possuem timestamp idêntico de recebimento:
   - *Solução adotada:* Critério explícito e documentado: (1) Data/Hora de recebimento; (2) Menor número de processo SEI; (3) ID de submissão no sistema (garantindo determinismo absoluto).
3. **Nomenclatura e Efeito de Resultados de Revisão:** Termos como `PRE_HABILITADO` e `PRE_INABILITADO` vs. `HABILITADO` e `INABILITADO`.
   - *Solução adotada:* Estados de revisão modelados como enum configurável no Edital, refletindo os status históricos sem perda de rastreabilidade.
4. **Impacto de Diligência Pendente no Ranking:** Se um processo em diligência é excluído temporariamente do snapshot de ranking preliminar ou se figura com pendência anotada.
   - *Solução adotada:* Processos em `PENDING_DILIGENCE` não são considerados elegíveis para ranking preliminar até conclusão da diligência (`ELIGIBLE_FOR_RANKING`), com flag explícita configurável.

---

## 6. Critérios de Aceite Globais

- [ ] Aplicação executa localmente e via container Docker com PostgreSQL.
- [ ] Todas as migrações executam limpas a partir do zero (`python manage.py migrate`).
- [ ] Django system checks passam sem erros (`python manage.py check`).
- [ ] Suíte de testes com cobertura abrangente executa e passa com sucesso via `pytest`.
- [ ] Linter e formatador (`ruff`) passam sem violações.
- [ ] Isolamento de analistas garantido por testes de segurança (GET e POST/PUT).
- [ ] Máquina de estados de workflow auditada a cada transição.
- [ ] Importador legado lê planilha XLSX sintética/real sem mutação e gera relatório de avisos e proveniência.
- [ ] Métrica do snapshot de referência (282 processos, G1=9, G2=34, G3=212, sem grupo=27) testada no harness de paridade.
- [ ] Trilha de auditoria completa gerada em eventos de mutação e transição.

---

## 7. Estratégia de Compatibilidade com a Planilha Legada

1. **Separação de Camadas:** As peculiaridades do Excel (colunas com mesclas, fórmulas pontuais, strings com quebras de linha, números formatados como texto) são isoladas exclusivamente no módulo `apps.legacy_import`. O núcleo do domínio Django não contém referências ou acoplamento a Excel.
2. **Mapeamento Explícito Documentado:** Cada aba e coluna do arquivo histórico possui mapeamento formal registrado em `docs/legacy-excel-mapping.md`.
3. **Idempotência e Rastreabilidade:** Cada linha importada armazena metadados de proveniência (`legacy_sheet_name`, `legacy_row_number`, `import_batch_id`), permitindo reimportação e verificação cruzada.
4. **Harness de Paridade (Golden Master):** Testes parametrizados em `tests/legacy/` comparam os cálculos realizados pelo `EvaluationService`, `ClassificationService` e `RankingService` contra os valores registrados na planilha, registrando divergências detalhadamente.
