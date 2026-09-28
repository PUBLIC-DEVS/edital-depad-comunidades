# Plataforma de Gestão e Análise de Editais — DEPED / MDS

Sistema Django monolítico para gestão, análise documental, revisão de conformidade, classificação determinística e auditoria de editais públicos de acolhimento social e comunidades terapêuticas, desenvolvido para o **Ministério do Desenvolvimento e Assistência Social, Família e Combate à Fome (MDS)**.

Substitui com total rastreabilidade, isolamento de segurança e performance a antiga operação realizada via planilhas compartilhadas no Excel Online / SharePoint.

---

## 1. Visão Geral e Objetivos

O sistema transforma a antiga operação de planilhas em uma aplicação web segura e auditável:

- **Abas do Excel** &rarr; Filas de trabalho específicas com controle de acesso baseado em papéis (RBAC).
- **Fórmulas Quebradiças** &rarr; Regras de domínio explícitas, determinísticas e testadas em serviços dedicados.
- **Células Editáveis** &rarr; Registros relacionais com trilha de auditoria append-only (`AuditEvent`).
- **Conferências Manuais** &rarr; Validações automáticas, detectores de anomalias cadastrais e filas de exceção.

---

## 2. Arquitetura e Estrutura de Diretórios

O projeto segue o padrão Monólito Modular Django:

```
edital-depad-comunidades/
├── config/                  # Configurações globais (settings, urls, wsgi, asgi)
├── apps/
│   ├── accounts/            # Custom User model, RBAC, adaptadores de autenticação
│   ├── editais/             # Editais, regras de financiamento, requisitos e subcritérios
│   ├── institutions/        # Entidades proponentes, normalização de CNPJ e municípios
│   ├── submissions/         # Inscrições, atribuições, fluxo e serviços de validação
│   ├── evaluations/         # Análise documental, checklist e cálculo de aptidão
│   ├── reviews/             # Fila de revisão de conformidade e diligências
│   ├── ranking/             # Classificação G1/G2/G3 e snapshots imutáveis de ranking
│   ├── reporting/           # Painel operacional de métricas e detecção de exceções
│   └── audit/               # Registro append-only de eventos de auditoria
├── templates/               # Django Templates organizados por domínio com Tailwind e HTMX
├── static/                  # Estilos institucionais (Design System), CSS e scripts
├── tests/
│   ├── unit/                # Testes unitários de serviços, CNPJ, modelos e regras
│   └── integration/         # Testes de integração de fluxo, isolamento e paridade
└── docs/                    # Documentação técnica, ADRs e relatórios de auditoria
```

---

## 3. Como Rodar Localmente

### 3.1 Pré-requisitos
- Python 3.12+
- PostgreSQL (opcional em desenvolvimento, fallback automático para SQLite)
- Git

### 3.2 Passo a Passo

```bash
# 1. Clone o repositório e acesse a pasta
git clone <url-do-repositorio>
cd edital-depad-comunidades

# 2. Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instale as dependências (incluindo pacotes de desenvolvimento)
pip install -e ".[dev]"

# 4. Configure o arquivo de ambiente
cp .env.example .env

# 5. Aplique as migrações do banco de dados
python manage.py migrate

# 6. Popule os dados de demonstração com usuários e processos realistas
python manage.py seed_demo

# 7. Inicie o servidor de desenvolvimento
python manage.py runserver
```

Acesse a plataforma em: `http://localhost:8000/`

---

## 4. Como Rodar com Docker & Compose

```bash
# Constrói as imagens e inicia os containers da aplicação e do PostgreSQL
docker compose up --build -d

# Executa as migrações no container
docker compose exec web python manage.py migrate

# Popula o cenário de demonstração
docker compose exec web python manage.py seed_demo
```

Acesse em: `http://localhost:8000/` (Health check: `http://localhost:8000/health/`)

---

## 5. Papéis de Usuário e Credenciais de Demonstração

O comando `python manage.py seed_demo` cria os seguintes usuários padrão:

| Papel | Login | Senha | Atribuições Principais |
| :--- | :--- | :--- | :--- |
| **Administrador** | `admin` | `admin12345` | Parâmetros de edital, criação de regras e superusuário. |
| **Coordenador** | `coordenador` | `coord12345` | Visão geral, redistribuição, homologação de ranking e exceções. |
| **Distribuidor** | `distribuidor` | `dist12345` | Triagem de novas inscrições e atribuição de carga aos analistas. |
| **Analista 1** | `ana.paula` | `analista12345` | Análise documental dos processos atribuídos a si (isolamento estrito). |
| **Analista 2** | `daniel.silva` | `analista12345` | Análise documental dos processos atribuídos a si (isolamento estrito). |
| **Analista 3** | `carlos.eduardo` | `analista12345` | Análise documental dos processos atribuídos a si (isolamento estrito). |
| **Revisor** | `revisor` | `revisor12345` | Revisão de conformidade em processos concluídos pelos analistas. |
| **Consulta** | `consulta` | `consulta12345` | Acesso de leitura para órgãos de controle e auditoria externa. |

---

## 6. Fluxo Operacional do Processo

```
[Inscrição Protocolada]
         │
         ▼
[Triagem & Distribuição] ──(Distribuidor atribui)──► [Em Análise pelo Analista]
                                                              │
                                                     (Conclusão do checklist)
                                                              │
                                                              ▼
                                                   [Pendente de Revisão]
                                                              │
                    ┌─────────────────────────────────────────┴─────────────────────────────────────────┐
                    ▼                                                                                   ▼
         [Revisão Confirmada]                                                                [Diligência Aberta]
                    │                                                                                   │
                    ▼                                                                                   ▼
      [Classificação & Ranking]                                                              [Resposta & Saneamento]
   (G1: Mulheres / G2: PRONASCI / G3: Ampla)
                    │
                    ▼
          [Snapshot Publicado]
```

---

## 7. Importador do Excel Legado & Harness de Paridade

Para importar planilhas históricas operadas no Excel Online:

```bash
# Execução direta com relatório detalhado
python manage.py import_legacy_edital caminho/do/arquivo.xlsx

# Simulação sem alteração no banco (dry-run)
python manage.py import_legacy_edital caminho/do/arquivo.xlsx --dry-run
```

### Números de Referência da Paridade (282 Processos):
- **Total de Processos Protocolados:** 282
- **Grupo 1 (G1 - Mulheres e Mães Nutrizes):** 9
- **Grupo 2 (G2 - Masculino PRONASCI):** 34
- **Grupo 3 (G3 - Masculino Demais Municípios):** 212
- **Sem Grupo (Vagas Zeradas / Pendentes):** 27

A conformidade matemática exata pode ser executada a qualquer momento via:
```bash
pytest -m legacy
```

---

## 8. Guia de Transição para o Backend Microsoft Entra ID

O sistema foi arquitetado com a camada de isolamento `apps.accounts.adapters`:

- **Ambiente Atual (Local):** `AUTH_ADAPTER = "local"` utiliza autenticação Django nativa via banco de dados.
- **Ambiente Futuro (MDS / Entra ID):**
  1. Configurar as variáveis no `.env`:
     ```env
     AUTH_ADAPTER=microsoft
     AZURE_TENANT_ID=<id-do-tenant-mds>
     AZURE_CLIENT_ID=<id-do-aplicativo-azure>
     AZURE_CLIENT_SECRET=<segredo-da-aplicacao>
     ```
  2. O backend `apps.accounts.adapters.microsoft.MicrosoftEntraAuthAdapter` mapeará automaticamente os claims `oid`, `upn`, e grupos de segurança institucionais para os papéis do sistema (`ANALISTA`, `REVISOR`, `COORDENADOR`, etc.).

---

## 9. Testes Automatizados e Qualidade

```bash
# Executa todos os testes unitários e de integração
pytest

# Executa testes com relatório de cobertura
pytest --cov=apps --cov-report=term-missing

# Verifica regras de linter
ruff check .

# Formatação automática de código
ruff format .
```

Consulte a pasta `docs/` para especificações adicionais:
- [Plano de Implementação](docs/IMPLEMENTATION_PLAN.md)
- [Modelo de Domínio & Diagrama ER](docs/domain-model.md)
- [Design System & UI Guidelines](docs/design-system.md)
- [Diretrizes de Segurança & Hardening](docs/security.md)
- [Estratégia de Testes](docs/testing.md)
- [Mapeamento do Excel Legado](docs/legacy-excel-mapping.md)
- [Relatório de Paridade Legada](docs/LEGACY_PARITY.md)
- [Decisões Arquiteturais (ADRs)](docs/adr/)