# Modelo de Domínio — Sistema de Gestão e Análise de Edital

Este documento descreve a arquitetura de entidades do sistema, seus relacionamentos e regras de integridade, substituindo a estrutura de abas e células do Excel legadão por um modelo relacional auditável em PostgreSQL.

---

## Diagrama Entidade-Relacionamento (ERD)

```mermaid
erDiagram
    User ||--o{ Assignment : "responsavel / atribuidor"
    User ||--o{ Evaluation : "avalia"
    User ||--o{ Review : "revisa"
    User ||--o{ Diligence : "solicita"
    User ||--o{ RankingSnapshot : "gera"
    User ||--o{ AuditEvent : "executa"

    Edital ||--o{ ProgramMunicipality : "possui"
    Edital ||--o{ FundingRule : "define"
    Edital ||--o{ Requirement : "estabelece"
    Edital ||--o{ Submission : "recebe"
    Edital ||--o{ RankingSnapshot : "origina"

    Municipality ||--o{ ProgramMunicipality : "vincula_programa"
    Municipality ||--o{ Institution : "sedia"
    Municipality ||--o{ Submission : "local_execucao"

    Institution ||--o{ Submission : "inscreve"

    Requirement ||--o{ RequirementCheck : "contem_subcriterios"

    Submission ||--o{ Assignment : "possui_historico"
    Submission ||--o| Evaluation : "possui_analise"
    Submission ||--o{ Review : "possui_revisoes"
    Submission ||--o{ Diligence : "possui_diligencias"
    Submission ||--o{ RankingEntry : "classificada_em"

    Evaluation ||--o{ CheckResult : "contem_resultados"
    Evaluation ||--o| Review : "objeto_de"

    RequirementCheck ||--o{ CheckResult : "avaliada_por"

    CheckResult ||--o{ ReviewItemDecision : "decidida_em"
    Review ||--o{ ReviewItemDecision : "contem_decisoes"

    RankingSnapshot ||--o{ RankingEntry : "composto_por"
```

---

## Descrição dos Domínios e Entidades

### 1. Núcleo Institucional e Municípios (`apps.institutions`)
- **`Municipality`**: Registra municípios com chave primária natural/oficial pelo **Código IBGE de 7 dígitos** (`ibge_code`), nome e UF. Elimina divergências causadas por variações de acentuação ou grafia textual.
- **`Institution`**: Representa a organização da sociedade civil proponente. O campo `cnpj` é validado e normalizado pelo módulo dedicado `apps.institutions.cnpj`, suportando tanto o padrão numérico clássico (14 dígitos) quanto a nova especificação alfanumérica da Receita Federal.

### 2. Parâmetros e Regras do Edital (`apps.editais`)
- **`Edital`**: Entidade versionável que armazena número, ano, vigência, status, versão de regras e política de duplicidade (`KEEP_EARLIEST_SUBMISSION` vs `KEEP_LATEST_SUBMISSION`). Garante que modificações futuras em editais novos não alterem retroativamente o histórico de editais encerrados.
- **`ProgramMunicipality`**: Mapeia a adesão de municípios a programas prioritários vinculados ao edital (ex: **PRONASCI**), base essencial para o enquadramento no Grupo 2 (G2).
- **`FundingRule`**: Parametriza valores mensais por vaga, duração em meses e percentual de patrimônio líquido mínimo exigido, evitando números mágicos no código.
- **`Requirement`**: Requisitos formais (ex.: `4.2-I`, `4.2-V Estatuto`, `4.2-XVI`).
- **`RequirementCheck`**: Subcritérios atômicos de cada requisito (ex.: finalidade estatutária, ausência de remuneração de dirigentes, dissolução patrimonial).

### 3. Inscrições e Distribuição (`apps.submissions`)
- **`Submission`**: Registro unificado da inscrição, contendo processo SEI, data/hora de protocolo (`received_at`), vagas (femininas, masculinas, mães nutrizes), valores propostos, status de workflow e grupo preliminar.
- **`Assignment`**: Histórico de atribuição e redistribuição de processos aos analistas, registrando analista anterior, novo analista, responsável pela distribuição, timestamp e motivo.

### 4. Avaliação Documental (`apps.evaluations`)
- **`Evaluation`**: Análise conduzida pelo analista responsável, registrando status (`DRAFT`, `COMPLETED`), parecer calculado (`APTA`, `INAPTA`, `EM_ANALISE`) e códigos dos requisitos com pendência (`failed_requirement_codes`).
- **`CheckResult`**: Normalização individual por subcritério (status `ATENDE`, `NAO_ATENDE`, `NAO_ENVIADO`, `NAO_APLICAVEL`), número SEI do documento, folhas/páginas, data de validade de certidão, valor financeiro e notas. Substitui a dispersão de 80 colunas flat do Excel.

### 5. Revisão e Diligência (`apps.reviews`)
- **`Review`**: Revisão hierárquica/de conformidade sobre a `Evaluation`. Não duplica dados da análise; preserva a decisão do revisor (`PRE_HABILITADO`, `PRE_INABILITADO`).
- **`ReviewItemDecision`**: Confirmação ou divergência item a item em relação ao parecer do analista, exigindo justificativa obrigatória em caso de discordância.
- **`Diligence`**: Subfluxo formal de saneamento de pendências documentais, com registro de motivo, prazo limite, resposta da entidade e resultado do contraditório.

### 6. Classificação e Ranking (`apps.ranking`)
- **`RankingSnapshot`**: Snapshot imutável gerado em determinada data de publicação, gravando a versão das regras, política de duplicidade e responsável pela geração.
- **`RankingEntry`**: Posição ordinal no grupo (G1, G2, G3), timestamp de desempate, total de vagas e anotação de supressão por duplicidade.

### 7. Trilha de Auditoria (`apps.audit`)
- **`AuditEvent`**: Registro append-only de alterações e transições de workflow. Grava ator, timestamp, entidade, ID, ação executada, campo alterado, valor antigo, valor novo e metadados contextuais em JSON. Proíbe qualquer mutação ou exclusão via ORM.
