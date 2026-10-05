# Estado da implementação após auditoria — fase 15

O hardening preserva a arquitetura Django e corrige importação real, workflow, ownership de revisão, retorno de diligência, início de análise por POST, elegibilidade/exclusões do ranking, proteção de snapshots, RBAC global, invariantes no banco, finanças por tipo de vaga e exemplos oficiais de CNPJ. O adaptador Microsoft permanece boundary/scaffold, sem login Entra/OIDC/SharePoint implementado.

| Verificação | Resultado verificado |
| --- | --- |
| Baseline pytest | 67 passed |
| Pytest completo com XLSX real | 193 passed, zero falhas/erros/skips; 79.469s |
| Pytest legacy | 5 passed; testes sintéticos |
| Pytest legacy_real | 2 passed; status do comparador FAIL |
| Coverage apps + config | 87.67%; 2845/3245 statements |
| Ruff check / format | PASS / PASS; arquivos Python verificados conforme Ruff |
| Django check | Sem issues |
| makemigrations --check | Sem mudanças pendentes |
| git diff --check | Vazio na comparação com a base e no working diff |
| Migrations em banco isolado | Aplicadas; upgrade com regra financeira antiga preservada testado |
| XLSX | Hash inalterado; nenhum save da fonte |
| CI PostgreSQL 16 | PASS; 191 passed, 2 legacy_real deselected; [run 36510344583](https://github.com/PUBLIC-DEVS/edital-depad-comunidades/actions/runs/36510344583) |


A planilha externa foi executada e 282 processos foram comparados. Paridade: **FAIL**, com 302 ocorrências agregadas, incluindo diferenças deliberadas e problemas da fonte. Reconciliação histórica por SEI: 180 APTAS menos oito APTAS duplicadas = 172 classificados. O ranking operacional com revisões não foi emitido devido a empates cuja política permanece aberta.

Este documento substitui as conclusões excessivas da entrega anterior. A referência para arquivos, commits, migrations e pendências é [POST_AUDIT_HARDENING_REPORT.md](POST_AUDIT_HARDENING_REPORT.md); a evidência externa está em [REAL_LEGACY_PARITY.md](REAL_LEGACY_PARITY.md).

Readiness: adequado para PR de hardening e auditoria independente; não autoriza publicação de ranking ou uso em produção antes do saneamento/aceite das questões registradas. A CI PostgreSQL do código validado passou. Main e a branch base permanecem referências intactas.
