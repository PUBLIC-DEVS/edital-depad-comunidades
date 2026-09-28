# Estratégia de Testes e Garantia da Qualidade — DEPED/MDS

Este documento descreve a arquitetura de testes automatizados, cobertura em camadas e diretrizes de execução contínua.

---

## 1. Pirâmide e Camadas de Teste

A plataforma adota uma abordagem de testes em três camadas complementares:

```
          / \
         /   \     Testes de Paridade Legada (@pytest.mark.legacy)
        /  *  \    (Workbook sintético com 282 processos, idempotência e paridade matemática)
       /-------\
      /         \    Testes de Integração (Workspaces, RBAC, Isolamento, HTMX)
     /    ***    \   (Intake, Triagem, Workspace Documental, Revisão, Diligência, Ranking)
    /-------------\
   /               \   Testes Unitários de Domínio (Services e Modelos)
  /     *******     \  (CNPJ, Regras Financeiras, Workflow FSM, Classificação, Duplicidades)
 /-------------------\
```

---

## 2. Estrutura dos Módulos de Teste

```
tests/
├── unit/
│   ├── test_cnpj.py                             # Validação e normalização de CNPJ numérico e alfanumérico
│   ├── test_domain_models.py                    # Modelos, restrições e append-only de AuditEvent
│   ├── test_evaluation_service.py               # Cálculo imperativo de aptidão/inaptidão
│   ├── test_workflow_service.py                 # Máquina de estados finita e transições válidas
│   ├── test_funding_service.py                  # Cálculos de valores e patrimônio sem hardcoding
│   ├── test_duplicates_service.py               # Políticas de duplicidade (mais antigo vs retificador)
│   ├── test_classification_and_ranking_service.py # Enquadramento G1/G2/G3/sem grupo e ordenação SEI
│   └── test_permissions_and_isolation.py        # Políticas de RBAC e isolamento de analistas
├── integration/
│   ├── test_submissions_intake_and_distribution.py # Triagem, busca, anomalias e distribuição
│   ├── test_evaluation_workspace.py             # Workspace documental com HTMX e isolamento
│   ├── test_reviews_and_diligence.py            # Fila de revisão, justificativas e diligências
│   ├── test_ranking_flow.py                     # Geração de ranking, imutabilidade e exportação CSV
│   ├── test_reporting_dashboard.py              # Métricas em tempo real e painel de exceções
│   └── test_legacy_parity.py                    # Paridade exata contra universo de 282 processos
└── test_bootstrap.py                            # Health check, migrações e bootstrap inicial
```

---

## 3. Instruções de Execução

### 3.1 Execução Completa da Suíte
```bash
pytest
```

### 3.2 Execução com Relatório de Cobertura de Código
```bash
pytest --cov=apps --cov-report=term-missing
```

### 3.3 Execução Apenas do Harness de Paridade Legada
```bash
pytest -m legacy
```

### 3.4 Execução de Testes Específicos por Arquivo
```bash
pytest tests/unit/test_cnpj.py
pytest tests/integration/test_evaluation_workspace.py
```

---

## 4. Verificação de Linter e Formatação

O projeto utiliza **Ruff** para linting ultra-rápido e formatação padronizada:

```bash
# Executa análise estática de código
ruff check .

# Aplica correções automáticas
ruff check --fix .

# Verifica consistência de formatação
ruff format --check .

# Formata o código
ruff format .
```

---

## 5. Integração Contínua (CI)

Todo pull request ou push na branch `feature/**` ou `main` aciona o pipeline GitHub Actions (`.github/workflows/ci.yml`), que valida:
1. Lint e formatação de código com Ruff.
2. Checagem estática do Django (`manage.py check`).
3. Verificação de migrações pendentes (`manage.py makemigrations --check --dry-run`).
4. Execução da suíte completa de testes no PostgreSQL 16.
5. Geração de relatório de cobertura de código.
