# edital-depad-comunidades

Plataforma Django para criar e executar **novos editais configuráveis**: cadastro de grupos, requisitos, subcritérios, evidências, finanças, programas/municípios, publicação versionada, processos, distribuição, análise, revisão, diligência, ranking e métricas. Toda essa operação funciona sem Excel. Veja [o relatório da Fase 16](docs/CRUD_PRODUCTIZATION_REPORT.md) e [a fronteira do legado](docs/legacy-boundary.md).

A planilha histórica continua disponível apenas para migração e regressão. O golden master real permanece `FAIL` nas diferenças já documentadas; testes verdes do comparador não transformam isso em paridade aprovada. Consulte [o relatório de hardening](docs/POST_AUDIT_HARDENING_REPORT.md), [a comparação real](docs/REAL_LEGACY_PARITY.md) e [o resumo sanitizado](artifacts/legacy-real-summary.json).

Para a configuração funcional do Edital 2026, consulte o [mapeamento da base](docs/EDITAL_2026_BASE_MAPPING.md), as [decisões ainda abertas](docs/EDITAL_2026_OPEN_DECISIONS.md) e o [relatório desta adaptação](docs/EDITAL_2026_ADAPTATION_REPORT.md). O HTTP integration lifecycle configura pelas views/forms os 14 blocos e 23 checks sem abrir o XLSX.

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

`seed_demo` constrói um edital com quatro grupos, regras financeiras e processos fictícios, sem `import_legacy_edital`. O comando informa os logins; a senha de demonstração local pode ser definida por `DEMO_PASSWORD`. Não execute o seed em produção. Para testar o produto sem carregar o app legado, use `ENABLE_LEGACY_IMPORT=false` antes de `migrate`, `seed_demo` e `runserver`. Uma instalação apenas do núcleo pode usar `pip install -e .`; o extra `.[legacy]` instala `openpyxl` quando a migração histórica for necessária.

Com Docker (caminho oficial recomendado; consulte o [Guia de Desenvolvimento Local](docs/LOCAL_DEVELOPMENT.md)):

```bash
./scripts/dev-check.sh
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```

Aplicação: `http://localhost:8000/`; health check: `/health/`.

## Criar um edital sem Excel

Entre como `ADMINISTRADOR` e abra `/administracao/` → **Editais** → **Novo edital**. Preencha número, ano, abertura/encerramento e versão. Na visão geral, cadastre grupos/públicos, requisitos, subcritérios e evidências, política de classificação, regras financeiras e vínculos de programas/municípios; crie analista e revisor em **Usuários e perfis**. O checklist exibe o que falta antes de **Publicar edital**. A publicação grava um snapshot imutável das regras. Para outra edição, use **Duplicar edital**; apenas a configuração é copiada.

O CRUD permite ajustar nomes e códigos de requisitos, ordem, obrigatoriedade, checks, status aceitos, evidências, validadores tipados, grupos, regra financeira, referência do programa e política de classificação. Use **Pré-visualizar formulário do analista** antes de publicar. As restrições contratuais são fontes configuráveis e auditadas; a duplicidade de novos editais começa como alerta `WARN_ONLY`. Uma divergência de CNPJ aparece na análise e só pode ser corrigida pela ação explícita de Administração/Coordenação, com justificativa e confirmação, antes da avaliação ou durante análise em rascunho. A operação reassocia somente a candidatura e preserva documentos; decisões concluídas e correções para CNPJ restrito durante análise não são alteradas por essa ação. A validação automática de datas requer a data oficial de referência definida pela coordenação.

Para criar uma edição rascunho a partir da configuração 2026 de desenvolvimento, cadastre primeiro um usuário administrador e informe datas operacionais explícitas:

```bash
python manage.py seed_edital_2026_base \
  --admin admin \
  --number 2026-BASE \
  --opens-at 2026-01-01T09:00:00-03:00 \
  --closes-at 2026-12-31T18:00:00-03:00
```

O comando não escolhe uma data de referência jurídica nem inventa a lista de municípios PRONASCI. Preencha esses dados e resolva as decisões abertas na interface antes da publicação. O seed é auxiliar; o teste principal cria a mesma configuração via telas HTTP.

O distribuidor usa `/processos/novo/` ou `/processos/importar-csv/` e atribui processos individuais/em lote. O analista atribuído inicia por POST, salva a análise dinâmica e conclui. `APTA` segue para ranking sem revisão automática; `INAPTA` vai a revisão não atribuída. O revisor assume a revisão, registra decisões de todos os itens impeditivos e conclui um parecer coerente. Uma diligência saneada retorna ao estágio de origem. Coordenador/Admin geram ranking; métricas exibem separadamente análise inicial e resultado consolidado. Consulte [o roteiro e as permissões](docs/CRUD_PRODUCTIZATION_REPORT.md).

O ranking oficial admite somente elegíveis, suprime duplicatas das posições quando a política configurada determina supressão e preserva exclusões auditáveis. Com `WARN_ONLY`, candidaturas duplicadas são mantidas e sinalizadas. Empates absolutos permanecem bloqueados enquanto a política estiver `UNRESOLVED`. Snapshots, entradas e exclusões são protegidos nas rotas/ORM comuns. Uma avaliação iniciada bloqueia redistribuição até haver operação formal de transferência. Desativar restrição não reabre processos: Administração/Coordenação deve usar **Liberar bloqueio pré-análise**, após todas as fontes cessarem, para retornar à recepção sem atribuição automática.

## Importação histórica e golden master

Para usar os comandos históricos, instale `pip install -e ".[legacy]"` e mantenha `ENABLE_LEGACY_IMPORT=true`. O XLSX histórico fica fora do Git e é sempre somente leitura. Coordenadas e normalizações estão em `apps/legacy_import`; consulte [o schema](docs/LEGACY_IMPORT_SCHEMA.md). A instituição é resolvida por CNPJ, o processo por edital + SEI e os eventos repetidos de diligência por hash + aba + linha.

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

## Remediação da auditoria 17.1

Veja [o relatório de correções e validações](docs/PHASE_17_1_REMEDIATION_REPORT.md). Comprovação do Anexo III é obrigatória quando aplicável, com N/A permitido; validators exigem evidências coletáveis antes da publicação. Manual e CSV compartilham triagem, CEP é administrável e exports operacionais são protegidos contra fórmulas. O teste automatizado permanece integração HTTP; homologação em navegador ainda é necessária.
