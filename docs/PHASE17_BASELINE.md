# Fase 17 — baseline

Capturado antes das alterações funcionais em 2026-09-29.

- Repositório: `/Users/daniel/Documents/mds/edital-depad-comunidades`
- Branch de trabalho criada a partir de `feature/edital-crud-productization`
- Base: `fc185fee64df818cc28a19d010f66566dd4b83ec`
- `main`: `230ec63b49dffe4263ca4c8336216cf84d19aee8`
- Remote `origin`: `https://github.com/PUBLIC-DEVS/edital-depad-comunidades.git`
- Árvore inicial limpa; ZIP de referência está ignorado por Git.

## Verificações

- `python manage.py check`: sem problemas.
- `python manage.py makemigrations --check`: nenhuma migration pendente.
- `pytest -q`: 211 passaram, 2 pulados. Os pulos são os testes da planilha legada real porque `LEGACY_XLSX_PATH` não estava definido; eles não indicam paridade.
- `ruff check .`: passou.
- `ruff format --check .`: 157 arquivos formatados.
- `git diff --check`: sem saída.

## Especificação recebida

Arquivo local somente para leitura: `Análise Edital 2026.xlsx`.

- SHA-256 no baseline: `9d405bf8aaea8ac5016bb3e7a6157cf25f23c0c6929094fb5daa7c776d83e918`.
- Abas: `DISTRIBUIÇÃO`, `ANALISTA`, `REGRAS`.
- `DISTRIBUIÇÃO`: 21 colunas; contém cabeçalhos de processo, recebimento, instituição, endereço, município/UF, CEP, vagas, capacidade, grupo e analista.
- `ANALISTA`: 81 colunas; cabeçalhos organizados em anexos/requisitos e campos de evidência.
- `REGRAS`: 23 linhas; registra triagem de contrato, alerta de duplicidade, grupos, validade documental, CNPJ declarado no Anexo I e encaminhamento para revisão/classificação.
- Não foram encontrados dados preenchidos nem fórmulas relevantes. Nenhuma gravação foi feita no workbook.
