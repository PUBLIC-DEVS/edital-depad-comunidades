# Fase 17.1 — Baseline de remediação

- Base auditada: `feature/edital-2026-base-adaptation` / `dcbe499408ab47a662006172e3cf3dfa182714d6`.
- Branch de trabalho: `feature/edital-2026-audit-remediation`.
- Main preservada: `230ec63b49dffe4263ca4c8336216cf84d19aee8`.
- Árvore inicialmente limpa; fetch/prune e pull ff-only executados, sem atualização da base.
- Ambiente limpo da auditoria: Python 3.12.8, Django 5.2.17; SQLite temporário e bytecode fora do repositório. Nenhuma dependência nova.
- LEGACY_XLSX_PATH ausente: testes reais históricos permanecem NOT_RUN.

| Verificação | Exit code | Duração (s) | Resultado |
|---|---:|---:|---|
| python | 0 | 0.01 | Python 3.12.8 |
| django | 0 | 1.26 | 0 issues |
| migrations | 0 | 0.27 | No changes detected |
| pytest | 0 | 50.63 | 229 passed, 2 skipped |
| no_legacy | 0 | 20.45 | 217 passed |
| legacy | 0 | 26.19 | 7 passed, 224 deselected |
| ruff | 0 | 0.1 | All checks passed |
| format | 0 | 0.02 | 172 files already formatted |
| diff | 0 | 0.02 | Saída vazia |

Contagens iguais às reproduzidas na auditoria; durações variam. Coverage anterior: 83%; será medida novamente na validação final.

Logs completos de execução preservados fora do Git em `/private/tmp/phase17-1-validation/`.
