# Real historical schema

The source is opened twice, for formula text and cached values, and never saved. Coordinates live in `apps/legacy_import/schema.py`. Only names starting exactly with `ANÁLISE -` identify individual analysts.

Distribution headers are row 2; rows begin at 3. SEI is E, CNPJ D, name C, timestamp combines F/G. Analyst/review/diligence SEI is C, starting at row 4. PRONASCI names come from CLASSIFICAÇÃO Z, with original spelling retained; unresolved municipalities have no IBGE code. Neither identities nor dates are fabricated.

Strict mode rolls back domain changes on source errors while retaining the run and structured issues. Lenient mode preserves safe historical identities and records every rejection/unknown value. A malformed timestamp excludes the process; an absent institution name remains empty with a warning. Existing operational data is not silently overwritten. Import timestamps record ingestion only.

The actual BY formula treats AG as an equity **status**, ignores AW in eligibility, and accepts ISENTO/ENVIADO only for BV. BZ nevertheless lists AW and BV failures. Per-check configuration preserves this historical distinction. CNPJ, pages, document numbers and validity dates are evidence attributes, not checks. No universal spreadsheet formula evaluator is used.

Reviews preserve CG decisions and missing reviewers. Diligences are separate source-row events, with unknown operational status and nullable deadline/request date/requester. Their existence is not evidence that a deadline or legal outcome was specified. SHA-256 + sheet + row + edital identifies repeated historical events. A different workbook hash is a new source version requiring reconciliation.

Every import run retains source cells, formulas, entity links and issues outside operational models. Real private database/CSV outputs and XLSX files are ignored by Git. The synthetic fixture generator tests the importer only and confers no real parity verdict.
