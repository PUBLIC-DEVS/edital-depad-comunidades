# Fronteira do legado

`apps/legacy_import` existe para ler o XLSX histórico, migrar registros, registrar proveniência e executar regressão/golden master. Suas coordenadas, nomes de abas e normalizações são detalhes dessa fronteira. O XLSX real permanece externo, somente para leitura, e seus relatórios por processo ficam em `artifacts/private/`.

O produto novo cria editais por `/admin-editais/`, configura grupos/requisitos/checagens/finanças/programas por formulários, recebe processos por `/processos/novo/` ou CSV e calcula classificação/ranking a partir do banco. Nenhum service operacional, tela do analista ou comando `seed_demo` importa o parser, o gerador sintético ou constantes do Excel.

O app é optativo: `ENABLE_LEGACY_IMPORT=false` o remove de `INSTALLED_APPS`. `pip install -e .` instala o núcleo sem `openpyxl`; para executar migração/regressão, use `pip install -e ".[legacy]"` e habilite o app. A instalação `.[dev]` também inclui essa dependência para testes. Sem o app, `manage.py migrate`, `seed_demo` e `test_new_edital_full_lifecycle.py` foram executados com êxito.

O comando histórico `import_legacy_edital` pertence agora a `apps/legacy_import/management/commands`; o gerador de fixtures sintéticas também mora nesse módulo. Remover essa pasta e desabilitar o app não elimina o fluxo do novo edital. Bases existentes precisam manter as migrations históricas aplicadas/registradas; remoção física do app de uma instalação que já o utilizou exige planejamento de implantação e não apaga dados automaticamente.

O golden master continua com status `FAIL` nas diferenças observadas. Seu teste verde significa que o comparador detectou e registrou as divergências; não estabelece conformidade do produto novo com decisões manuais da planilha. O teste principal de aceitação da Fase 16 é o ciclo de vida sem Excel, executado também com o app legado desligado.
