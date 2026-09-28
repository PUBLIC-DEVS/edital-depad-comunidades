# Mapeamento da Planilha Excel Legada para o Modelo Relacional

Este documento detalha o mapeamento estrutural entre o modelo de planilhas Excel (anteriormente operado via Excel Online / SharePoint) e o modelo relacional de domínio da plataforma Django.

---

## 1. Visão Geral da Transição

| Elemento Legado (Excel Online) | Mecanismo Novo (Django Platform) | Justificativa Arquitetural |
| :--- | :--- | :--- |
| **Aba "DISTRIBUIÇÃO"** | `Submission` + `Assignment` + `WorkflowService` | Elimina risco de sobrescrita concorrente de linhas; atribuição formal auditável com histórico. |
| **Abas Individuais de Analistas** (`ANA PAULA`, `DANIEL`, etc.) | `Evaluation` + `CheckResult` normalizados | Evita 80 colunas horizontais desnormalizadas; isolamento no nível de linha (Row-Level Security). |
| **Aba "REVISÃO"** | `Review` + `ReviewItemDecision` | Registra confirmação ou divergência item a item sem copiar ou duplicar registros da análise original. |
| **Aba "DILIGÊNCIA"** | `Diligence` | Rastreamento formal de prazos, notificações e respostas com bloqueio e desbloqueio de workflow. |
| **Aba "CLASSIFICAÇÃO"** | `ClassificationService` + `RankingSnapshot` | Classificação determinística e reprodutível por snapshots imutáveis, em vez de ordenações manuais mutáveis. |
| **Aba "MÉTRICAS"** | `DashboardMetricsService` (`apps.reporting`) | Consultas agregadas em tempo real com drill-down para processos afetados, substituindo fórmulas `CONT.SE`. |
| **Abas Auxiliares (PRONASCI, Cidades)** | `Municipality` + `ProgramMunicipality` | Comparação confiável por Código IBGE de 7 dígitos, eliminando divergências por acentuação ou espaços. |

---

## 2. Dicionário de Campos e Mapeamento

### 2.1 Aba `DISTRIBUIÇÃO` &rarr; `Submission`, `Institution`, `Assignment`

| Coluna Excel Legada | Campo Django Destino | Tipo / Normalização | Observações |
| :--- | :--- | :--- | :--- |
| `Nº Processo SEI` / `Processo` | `Submission.processo_sei` | `CharField(max_length=50)` | Chave de negócio auditável. |
| `Data/Hora Protocolo` | `Submission.received_at` | `DateTimeField` | Base do critério de desempate temporal. |
| `CNPJ` | `Institution.cnpj` | `CharField(max_length=20)` | Validado e normalizado (14 dígitos ou alfanumérico RFB). |
| `Razão Social` / `Proponente` | `Institution.name` | `CharField(max_length=255)` | Cadastrado ou atualizado no `Institution`. |
| `Município` | `Municipality.name` | `ForeignKey(Municipality)` | Mapeado via tabela de municípios e código IBGE. |
| `UF` | `Municipality.state` | `CharField(max_length=2)` | Sigla do estado federado. |
| `Vagas Femininas` | `Submission.vagas_femininas` | `PositiveIntegerField` | Componente para enquadramento no Grupo 1 (G1). |
| `Vagas Mães Nutrizes` | `Submission.vagas_maes_nutrizes` | `PositiveIntegerField` | Componente para enquadramento no Grupo 1 (G1). |
| `Vagas Masculinas` | `Submission.vagas_masculinas` | `PositiveIntegerField` | Enquadramento nos Grupos 2 ou 3. |
| `Total Vagas Solicitadas` | `Submission.vagas_solicitadas` | `PositiveIntegerField` | Validado contra soma das partes e capacidade total. |
| `Capacidade Instalada` | `Submission.capacidade_total` | `PositiveIntegerField` | Validação de capacidade física vs proposta. |
| `Analista Responsável` | `Assignment.analyst` | `ForeignKey(User)` | Localiza usuário pelo nome/login e cria atribuição ativa. |

---

### 2.2 Abas de Analistas &rarr; `Evaluation`, `CheckResult`

| Elemento da Aba do Analista | Modelo Destino | Campo Destino | Regra de Conversão |
| :--- | :--- | :--- | :--- |
| Linha do Processo | `Evaluation` | `submission`, `analyst`, `status` | Cria `Evaluation` vinculada ao analista titular. |
| Colunas de Itens (ex: `4.2-I`, `4.2-V`, `4.2-XVI`) | `CheckResult` | `requirement_check` | Vincula ao subcritério do edital. |
| Valores das Células (`ATENDE`, `NÃO ATENDE`, `NÃO ENVIADO`, `N/A`) | `CheckResult` | `status` | Converte strings para choices padronizados: `ATENDE`, `NAO_ATENDE`, `NAO_ENVIADO`, `NAO_APLICAVEL`. |
| Campo Observações / Páginas | `CheckResult` | `notes`, `pages`, `sei_number` | Metadados de conferência documental. |
| Parecer Conclusivo do Analista | `Evaluation` | `result` | `APTA` ou `INAPTA`, conferido via `EvaluationService`. |

---

### 2.3 Aba `REVISÃO` &rarr; `Review`, `ReviewItemDecision`

| Elemento da Aba de Revisão | Modelo Destino | Campo Destino | Regra de Conversão |
| :--- | :--- | :--- | :--- |
| `Revisor` | `Review` | `reviewer` | Usuário revisor responsável. |
| `Parecer Preliminar` | `Review` | `preliminary_result` | `PRE_HABILITADO` ou `PRE_INABILITADO`. |
| `Itens com Divergência` | `ReviewItemDecision` | `agrees_with_analyst=False` | Registra parecer discordante e justificativa obrigatória. |
| `Fundamentação do Revisor` | `Review` | `decision_notes` | Texto livre com argumentação jurídica/técnica. |

---

### 2.4 Aba `DILIGÊNCIA` &rarr; `Diligence`

| Coluna Legada | Campo Django Destino |
| :--- | :--- |
| `Motivo da Diligência` | `Diligence.reason` |
| `Data de Abertura` | `Diligence.requested_at` |
| `Prazo Final` | `Diligence.deadline` |
| `Data da Resposta` | `Diligence.answered_at` |
| `Parecer Pós-Diligência` | `Diligence.result` (`SANEADA` / `NAO_SANEADA`) |
| `Status` | `Diligence.status` |

---

## 3. Garantias de Idempotência e Preservação

1. **Chave de Idempotência:** Toda submissão é identificada por `(edital, processo_sei)`. Importações subsequentes executam `update_or_create` sem duplicar instâncias.
2. **Entidades Proponentes:** As instituições são recuperadas ou criadas com base no CNPJ limpo e normalizado (`Institution.cnpj`).
3. **Municípios:** Mapeamento prioritário pelo código IBGE ou normalização `(nome, UF)`. Inconsistências não interrompem o processo, sendo reportadas no log de importação.
4. **Auditabilidade:** Cada entidade criada ou alterada durante a importação gera um evento `AuditEvent` informando o ator (`sistema/importador`), data/hora e fonte (`legacy_excel_import`).
