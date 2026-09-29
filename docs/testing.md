# Testes e limites da evidência

A suíte verifica regras de domínio, autorização nas views, ownership, IDOR, início de análise por POST, retorno de diligência, posições oficiais, exclusões, proteção dos snapshots, auditoria de transições, finanças Decimal, exemplos oficiais de CNPJ e preservação das regras financeiras antigas na migration.

```bash
python manage.py check
python manage.py makemigrations --check
pytest
pytest -m "not legacy_real"
pytest -m legacy
LEGACY_XLSX_PATH="/caminho/arquivo.xlsx" pytest -m legacy_real
pytest --cov=apps --cov=config --cov-report=term-missing
ruff check .
ruff format --check .
```

`legacy` contém casos sintéticos de schema/importação e segurança. `legacy_real` exige um arquivo externo e nunca o gera. Seus testes verificam o fingerprint conhecido, a completude dos diffs, preservação do SHA-256 e idempotência em processos Python separados usando banco isolado. Um status FAIL na comparação pode coexistir com testes verdes que comprovam que a divergência foi corretamente detectada e registrada.

Sem LEGACY_XLSX_PATH o teste real é SKIP explícito; arquivo indicado e inexistente é falha. Nenhum desses casos significa paridade aprovada. O status da execução privada é registrado no summary, não inferido do exit code de pytest.

CI pública executa `pytest -m "not legacy_real"` com PostgreSQL 16, Ruff, Django check e migration check. A execução privada/manual deve fornecer o XLSX por caminho externo e proteger os artefatos por processo; o workbook nunca é enviado ao repositório. A validação local desta fase usa SQLite; a CI PostgreSQL deve ser conferida antes de aprovar o PR.

Resultados finais, cobertura e limitações estão em [POST_AUDIT_HARDENING_REPORT.md](POST_AUDIT_HARDENING_REPORT.md) e `artifacts/final-audit.json`.
