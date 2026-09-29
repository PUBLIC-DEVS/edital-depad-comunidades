# edital-depad-comunidades

Sistema Django para inscrições, distribuição, análise documental, revisão, diligência e classificação do edital DEPED/MDS. Preserva o monólito modular, services de domínio, Django Templates, HTMX, RBAC e AuditEvent.

A fase 15 corrige regras identificadas pela auditoria. A paridade com a planilha histórica real está **FAIL**, com diferenças registradas por processo. Testes verdes do harness não equivalem a paridade aprovada. Consulte [o relatório de hardening](docs/POST_AUDIT_HARDENING_REPORT.md), [a comparação real](docs/REAL_LEGACY_PARITY.md) e [o resumo sanitizado](artifacts/legacy-real-summary.json).

## Ambiente local

Python 3.12+ e Django 5.2 LTS. O patch verificado é 5.2.17; a dependência fica na linha 5.2. PostgreSQL é o banco configurado na CI; SQLite atende desenvolvimento e testes locais.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

O cenário de demonstração usa dados sintéticos e credenciais de desenvolvimento. Nunca estabelece paridade histórica. O comando informa os logins; não execute o seed em produção.

Com Docker:

```bash
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```

Aplicação: `http://localhost:8000/`; health check: `/health/`.

## Fluxo e permissões

O analista atribuído inicia a avaliação por POST. Abrir o workspace por GET apenas consulta dados. APTA segue para ELIGIBLE_FOR_RANKING, sem revisão automática; INAPTA cria revisão pendente sem responsável. O revisor assume a revisão antes de editar. Uma avaliação iniciada bloqueia redistribuição até existir uma operação formal de transferência.

Diligência saneada retorna ao estágio de origem. Consequência de diligência não saneada exige configuração expressa do coordenador/admin; sem política, a conclusão é bloqueada. Registros históricos incompletos não recebem prazo, data ou solicitante inventados.

Ranking oficial admite somente estágios ELIGIBLE_FOR_RANKING/RANKED, elimina duplicatas das posições e registra exclusões separadas. O padrão histórico mantém a primeira inscrição absoluta por CNPJ. Empates absolutos permanecem bloqueados enquanto a política estiver UNRESOLVED. Snapshots, entradas e exclusões são protegidos por model, queryset, service e admin; acesso SQL privilegiado está fora dessa proteção.

| Papel | Escopo |
| --- | --- |
| ANALISTA | Processos atribuídos e próprias avaliações |
| REVISOR | Fila não atribuída e revisões assumidas; sem edição de revisão de outro responsável |
| DISTRIBUIDOR | Intake e distribuição |
| COORDENADOR | Visão global, métricas, ranking e operações autorizadas |
| ADMINISTRADOR | Visão global e configuração |
| CONSULTA | Leitura global autorizada; sem mutações |

Métricas, ranking, histórico e exports exigem ADMINISTRADOR/COORDENADOR/CONSULTA nas views. Admin de entidades operacionais é somente leitura; alterações passam pelos serviços auditados.

## Importação e golden master

O XLSX histórico fica fora do Git e é sempre somente leitura. Coordenadas e normalizações estão em `apps/legacy_import`; consulte [o schema](docs/LEGACY_IMPORT_SCHEMA.md). A instituição é resolvida por CNPJ, o processo por edital + SEI e os eventos repetidos de diligência por hash + aba + linha.

```bash
python manage.py import_legacy_edital "$LEGACY_XLSX_PATH" --strict
python manage.py import_legacy_edital "$LEGACY_XLSX_PATH" --lenient
```

Strict reverte entidades operacionais em caso de erros, mantendo run/issues. Lenient importa somente o que é seguro e preserva problemas estruturados. Dry-run também mantém o registro da execução e issues. Municípios sem identidade oficial conservam IBGE nulo.

Execute a auditoria em um banco isolado, sem recalcular nem salvar o XLSX:

```bash
export LEGACY_XLSX_PATH="/caminho/PLANILHA ANÁLISE EDITAL-13.xlsx"
export DATABASE_URL="sqlite:///artifacts/private/legacy-validation.sqlite3"
mkdir -p artifacts/private
python manage.py migrate
python manage.py audit_legacy_real --generate-snapshot --output artifacts/private
python manage.py audit_legacy_real --output artifacts/private
```

Os CSVs por processo, reconciliação, duplicidades e issues ficam em `artifacts/private/`, ignorado pelo Git. Use `--fail-on-mismatch` quando o job precisar falhar com qualquer status diferente de PASS. O comando sem arquivo informa NOT_RUN. A CI pública não recebe o workbook nem dados pessoais.

```bash
python manage.py check
python manage.py makemigrations --check
pytest -m "not legacy_real"
pytest -m legacy                  # Testes sintéticos, não paridade real
LEGACY_XLSX_PATH="/caminho/arquivo.xlsx" pytest -m legacy_real
pytest --cov=apps --cov=config --cov-report=term-missing
ruff check .
ruff format --check .
```

`legacy_real` sem variável é SKIP explícito e não gera PASS de paridade. Veja [a estratégia de testes](docs/testing.md).

## Autenticação institucional

`apps.accounts.adapters.microsoft.MicrosoftAuthAdapter` é uma **authentication boundary / adapter ready for integration**. Recebe claims já decodificados; não realiza sozinho validação JWT, descoberta OIDC, redirect/login Entra ou integração SharePoint. A integração do colaborador não foi localizada no checkout verificado. Login local continua disponível para desenvolvimento. Não trate esse scaffold como SSO implementado.
