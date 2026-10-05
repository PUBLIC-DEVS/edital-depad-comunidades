# Summary

This change delivers a configurable, auditable Django platform for creating and operating public edital workflows, including the coordinator’s 2026 functional specification. The complete development history is preserved in feature/edital-2026; no runtime code changed in the final documentation-only consolidation commit.

# Why

The operational goal is to manage new editais through the web product instead of depending on spreadsheets. The 2026 workbook was used as a functional specification for intake fields, documentary requirements, validations, groups, review, and classification. It is not an operational database or a runtime dependency.

# Architecture

- Django 5.2 LTS modular monolith, PostgreSQL, Django Templates, and HTMX.
- Domain services for intake, workflow, evaluation, review, diligence, classification, and ranking.
- Configurable Edital, requirements/checks, evidence fields, typed validators, target groups, financial rules, programs, and municipalities.
- RBAC and object-level access enforced server-side.
- No React SPA, microservices, BPMN engine, or arbitrary executable rule language.

# Functional Scope

- Create, edit, validate, publish, and clone editais through product screens.
- Configure requirements, subcriteria, accepted results, mandatory behavior, order, and evidence.
- Configure groups/classification policies, funding by vacancy type, programs and municipalities.
- Maintain institutions and process submissions; import CSV; distribute individually or in batches.
- Run document evaluation, review, diligence, ranking snapshots, metrics, exception queues, and CSV exports.
- Preserve audit events for workflow and material field changes.

# Edital 2026

The coordinator’s specification is represented as 14 documentary blocks and 23 decision checks: Anexos I, II, III and IV, Estatuto (seven checks), SICAF, election minutes, institutional address, legal representative, CNPJ, Fire Department license, sanitary license, therapeutic program, floor plan, and photo report.

Evidence fields are configured per check and the analyst workspace presents vertical sections/cards rather than an 81-column spreadsheet. Typed validations cover canonical CNPJ, document expiration, minimum CNPJ age, and expected CNAE. Publication rejects active validators whose required evidence is not collected.

Anexo III’s proof check is required when applicable and permits N/A: ATENDE satisfies; NÃO ATENDE results in INAPTA; permitted NÃO APLICÁVEL satisfies; a pending value leaves the evaluation in EM ANÁLISE and prevents conclusion. This behavior was corrected after independent audit.

# Security

- CSRF middleware and POST-only mutation endpoints.
- Role and object-level authorization on server-side views/services.
- Analyses and reviews are scoped by assignment/ownership; Consulta is read-only.
- CSV exports neutralize formula-leading user strings.
- GET workspaces/previews are read-only.
- Critical operations use transactions/locking; database constraints protect key identities and active assignment invariants.

# Auditability

AuditEvent is append-only through instance operations and protected QuerySet mutation methods. Events retain actor, timestamp, entity, field and old/new values where applicable. Workflow transitions, evaluation field changes, identity correction, restriction release, review decisions, diligence and ranking generation are auditable. Ranking snapshots/entries are immutable through the ordinary application paths.

# Legacy Boundary

legacy_import remains for migration, synthetic regression and historical audit only. New edital setup, intake, evaluation, classification and analyst screens do not require a workbook. The 2026 lifecycle also passed with ENABLE_LEGACY_IMPORT=false. The historical real-workbook parity test remains NOT_RUN when LEGACY_XLSX_PATH is absent.

# Testing

Validated results:

- Full suite: 295 passed, 2 skipped.
- ENABLE_LEGACY_IMPORT=false: 283 passed.
- Synthetic legacy marker: 7 passed.
- Phase 17.1 regression suite: 66 passed.
- Coverage report: 84.28%.
- Ruff lint/format, Django check, migration check and git diff --check: PASS.
- PostgreSQL 16 CI: PASS, run 36641868421, exact HEAD e09e64c3bb2e474acb923da77c7de7d277978d4d; the CI suite reported 295 passed, 2 deselected, and the no-legacy lifecycle reported 1 passed.

# Independent Audits

The independent Phase 17 audit identified gaps in conditional Anexo III semantics, identity recovery, intake screening, restriction release, validator/evidence compatibility, postal-code administration, CSV export safety, optional-financial anomalies, and preview/runtime parity. The Phase 17.1 remediation was reviewed independently and classified READY_FOR_PR. The final organization commit adds documentation only.

# Fixed Findings

- F17-01 conditional Anexo III check: FIXED.
- F17-02 formal, audited CNPJ correction: FIXED.
- F17-03 common manual/CSV intake pipeline: FIXED.
- F17-04 explicit pre-analysis restriction release: FIXED.
- F17-05 validator/evidence dependencies: FIXED.
- F17-06 institutional postal code CRUD: FIXED.
- F17-08 CSV formula injection neutralization: FIXED.
- F17-09 financial anomalies respect edital configuration: FIXED.
- F17-10 preview uses active checks consistently: FIXED.

# Deferred Findings

- F17-07 shared evidence UX: DEFERRED_TO_HOMOLOGATION.
- F17-11 workspace query optimization: DEFERRED_PRE_HOMOLOGATION.

Neither item blocks PR review. No large evidence-model refactor or query-architecture change was added.

# Business Decisions Still Open

The coordinator must decide the official reference date, CNAE principal/unique/presence semantics, definitive duplicate-submission policy, formal confirmation of mothers-nursing vacancies in G1, the authoritative PRONASCI municipality source, and the absolute-tie ranking rule. The application leaves these configurable or blocks publication/ranking where a safe decision is required; this PR does not choose legal policy.

# Deployment / Migration Notes

Run the existing Django migrations in the normal deployment process. No migration was introduced in Phase 17.1 or in this documentation commit. Validate environment configuration and database backup/restore in staging before production. No legacy workbook is needed to configure or run a new edital.

# Manual Validation Checklist

- Create an edital as ADMINISTRADOR, add groups, requirements/checks and validators, then inspect the analyst preview.
- Confirm publication is blocked when required configuration or validator evidence is missing.
- Publish the edital and create a process; check canonical CNPJ and restriction/duplicate warnings.
- Assign an analyst, complete an evaluation, and verify APTA routes to ranking eligibility while INAPTA routes to an unassigned Review.
- Claim and complete a Review; verify all blocking checks require a decision.
- Open and conclude a Diligence and confirm the stage return.
- Generate a ranking snapshot and verify only eligible entries receive positions.
- Review initial-result and consolidated-workflow metrics separately.
- Inspect audit history and verify read-only roles cannot mutate data.
- Run the lifecycle with ENABLE_LEGACY_IMPORT=false.

# Known Limitations

This is readiness for PR review, not production readiness or legal approval. Visual/browser homologation, staging, official source data, open coordinator decisions and final institutional authentication are still required. The test lifecycle uses Django HTTP Client/views/forms, not a real browser. Real historical workbook parity is not asserted.

# Review Guidance

Start review in:

- apps/editais/
- apps/submissions/
- apps/evaluations/
- apps/reviews/
- apps/ranking/
- apps/audit/
- tests/regression/

Then inspect the configuration-to-workspace lifecycle and the independent-audit remediation report. In particular, verify Anexo III’s applicable failure case, formal CNPJ reassociation, the shared intake service, restriction release, validator evidence requirements, and append-only audit behavior.

# Merge Notes

- Proposed base: main.
- Proposed compare/head: feature/edital-2026.
- This branch descends from the audited final branch and preserves the complete implementation history; intermediate branches do not need to be merged separately.
- No PR was opened and no merge was performed.
- No separate Microsoft/Entra authentication branch was found in the fetched refs. origin/login_test points to the main commit and contains no unique authentication work; the existing adapter remains a scaffold/boundary, not completed SSO.
