# Checklist após correção da auditoria

Data: 2026-09-28. Python 3.12.8 / Django 5.2.17. Resultado: pronto para auditoria independente, com paridade real **FAIL** e pendências explícitas. Não há aprovação de conformidade integral.

| Critério recebido | Estado | Evidência |
| --- | --- | --- |
| 1–3: schema, 282 processos e 11 analistas | VERIFICADO | Testes externos/fingerprint e parsing em colunas E/C corretas |
| 4: resultado inicial 180/102 | DIVERGÊNCIAS LISTADAS | 109 BY manuais; checks calculam 71/211, decisão do responsável documentada |
| 5–6: revisão real e diligência sem dados inventados | VERIFICADO | 216 revisões, 165 eventos; resultado/estado desconhecidos explícitos |
| 7–9: APTA/INAPTA e GET sem mutação | VERIFICADO | Regressões de workflow e workspace |
| 10–11: integridade do review e retorno de diligência | VERIFICADO | IDOR/ownership, queryset por evaluation; quatro origens testadas |
| 12–15: elegibilidade, exclusões, snapshots e auditoria | VERIFICADO | Posições consecutivas, ORM/admin protegidos, eventos RANKED |
| 16: fórmula financeira U/V | VERIFICADO COM DIFERENÇA DA FONTE | U coincide; um V cached vazio versus zero calculado |
| 17–19: RBAC, CNPJ positivo e LTS | VERIFICADO | Views/exports server-side; exemplos oficiais; Django 5.2.17 |
| 20: ausência de arquivo não gera paridade PASS | VERIFICADO | NOT_RUN/skip explícito; sintético separado |
| 21–25: diff, pytest, Ruff, Django e migrations | VERIFICADO LOCALMENTE E NA CI | Resultados detalhados abaixo; CI PostgreSQL aprovada |

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


[Avaliação completa](POST_AUDIT_HARDENING_REPORT.md), [paridade real](REAL_LEGACY_PARITY.md) e [evidência estruturada](../artifacts/final-audit.json). Resultados manuais mantidos no histórico não são usados para maquiar o cálculo. A linha sem SEI e os dois valores desconhecidos continuam issues da fonte. Não houve merge nem alteração de main.
