"""Golden master against external observations, with per-process differences.

Imported decisions are compared as imported decisions, never called independently calculated
legal outcomes. Source initial BY, consolidated BX, displayed metrics and classification are
separate observations. A missing real file can only yield NOT_RUN.
"""

import re
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.editais.models import ProgramMunicipality
from apps.evaluations.models import Evaluation
from apps.evaluations.services.evaluation import EvaluationService
from apps.institutions.cnpj import normalize_cnpj
from apps.institutions.models import Institution, Municipality
from apps.reviews.models import Diligence, Review
from apps.submissions.models import Assignment, Submission
from apps.submissions.services.duplicates import DuplicateService
from apps.submissions.services.funding import FundingRuleNotFoundError, FundingService

from .models import LegacyEntityLink, LegacyImportIssue, LegacySourceRecord
from .normalizers import (
    decimal_value,
    failed_codes,
    json_value,
    normalize_review,
    parse_timestamp,
    text,
)


def parity_status(real_executed, mismatches=0, incomplete=()):
    if not real_executed:
        return "NOT_RUN"
    if mismatches:
        return "FAIL"
    return "PARTIAL" if incomplete else "PASS"


def entity_counts(edital):
    return {
        "Submission": Submission.objects.filter(edital=edital).count(),
        "Institution": Institution.objects.count(),
        "Municipality": Municipality.objects.count(),
        "Assignment": Assignment.objects.filter(submission__edital=edital).count(),
        "Evaluation": Evaluation.objects.filter(submission__edital=edital).count(),
        "Review": Review.objects.filter(submission__edital=edital).count(),
        "Diligence": Diligence.objects.filter(submission__edital=edital).count(),
        "ProgramMunicipality": ProgramMunicipality.objects.filter(edital=edital).count(),
    }


def group_value(value):
    found = re.search(r"\bG[123]\b", text(value).upper())
    return (
        found[0]
        if found
        else "SEM_GRUPO"
        if not value or "SEM GRUPO" in text(value).upper()
        else text(value)
    )


def cents(value):
    value = decimal_value(value)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if value is not None else None


def _compare(row, field, expected, actual, code=None):
    row[field + "_excel"] = json_value(expected)
    row[field + "_sistema"] = json_value(actual)
    if expected != actual:
        row["mismatch_codes"].append(code or field.upper())


def _row(record):
    return {
        "processo_sei": record["processo_sei"],
        "sheet": record["sheet"],
        "row": record["row"],
        "mismatch_codes": [],
    }


def _positions(submissions):
    grouped, result = defaultdict(list), {}
    for sub in submissions:
        grouped[sub.target_group].append(sub)
    for group, members in grouped.items():
        # Absolute ties are left unresolved; source row order is only an observed Excel behavior.
        for pos, sub in enumerate(
            sorted(members, key=lambda s: (s.received_at, s.processo_sei)), 1
        ):
            result[sub.processo_sei] = (group, pos)
    return result


def compare_workbook(data, run, snapshot=None):
    edital = run.edital
    subs = {
        s.processo_sei: s
        for s in Submission.objects.filter(edital=edital)
        .select_related("institution", "municipality")
        .prefetch_related("assignments__analyst")
    }
    evaluations = {
        e.submission_id: e
        for e in Evaluation.objects.filter(submission__edital=edital).select_related(
            "analyst", "submission__edital"
        )
    }
    analyses = {r["processo_sei"]: r for r in data.analyses}
    rows = {
        area: []
        for area in (
            "submissions",
            "evaluations",
            "reviews",
            "diligences",
            "ranking",
            "reconciliation",
            "duplicates",
        )
    }
    incomplete = [
        "Legal review outcome is a stored decision, not derivable from initial checks",
        "Historical diligence dates, deadlines and legal effects are not established",
    ]
    for record in data.distribution:
        row, v = _row(record), record["values"]
        sub = subs.get(record["processo_sei"])
        if sub is None:
            row["mismatch_codes"].append("MISSING_SUBMISSION")
            rows["submissions"].append(row)
            continue
        _compare(row, "cnpj", normalize_cnpj(v["cnpj"]), sub.institution.cnpj)
        recovered = text(v["institution"]) or text(
            analyses.get(sub.processo_sei, {}).get("values", {}).get("institution")
        )
        _compare(row, "institution", recovered, sub.institution.name)
        try:
            expected = parse_timestamp(v["date"], v["time"], data.epoch)
        except (ValueError, TypeError, OverflowError):
            expected = None
        actual = timezone.localtime(sub.received_at)
        _compare(row, "timestamp", expected, actual)
        _compare(row, "date", expected.date() if expected else None, actual.date())
        _compare(row, "time", expected.time() if expected else None, actual.time())
        analyst = next(
            (a.analyst.first_name for a in sub.assignments.all() if a.status == "ACTIVE"), ""
        )
        _compare(row, "analyst", text(v["analyst"]), analyst)
        _compare(row, "state", text(v["state"]), sub.municipality.state if sub.municipality else "")
        _compare(
            row,
            "municipality",
            text(v["municipality"]),
            sub.municipality.name if sub.municipality else "",
        )
        for field in (
            "vagas_femininas",
            "vagas_masculinas",
            "vagas_maes_nutrizes",
            "vagas_solicitadas",
            "capacidade_total",
        ):
            _compare(row, field, int(decimal_value(v[field]) or 0), getattr(sub, field))
            row[field + "_raw"] = json_value(v[field])
        _compare(row, "group", group_value(v["group"]), sub.target_group)
        row["group_cache_available"] = v["group"] is not None
        try:
            total, equity = FundingService.calculate_submission_values(sub)
            for field, computed in (("valor_global", total), ("patrimonio_minimo", equity)):
                _compare(row, field, cents(v[field]), computed)
                row[field + "_stored"] = json_value(getattr(sub, field))
                row[field + "_raw"] = json_value(v[field])
        except FundingRuleNotFoundError:
            row["mismatch_codes"].append("FUNDING_RULE_NOT_CONFIGURED")
        rows["submissions"].append(row)
    calculated_results = {}
    for record in data.analyses:
        row = _row(record)
        sub = subs.get(record["processo_sei"])
        evaluation = evaluations.get(sub.pk) if sub else None
        if evaluation is None:
            row["mismatch_codes"].append("MISSING_EVALUATION")
        else:
            assessment = EvaluationService.calculate_assessment(evaluation)
            calculated_results[sub.processo_sei] = assessment.result
            _compare(
                row,
                "initial_result",
                text(record["values"]["result"]).replace(" ", "_"),
                assessment.result,
            )
            _compare(
                row,
                "failed_requirements",
                failed_codes(record["values"]["failed"]),
                assessment.failed_requirement_codes,
            )
            row["initial_result_formula"] = record["formulas"].get("BY")
            row["initial_result_is_literal"] = "BY" not in record["formulas"]
            row["failed_requirements_raw"] = record["values"]["failed"]
            row["failed_check_columns"] = [
                c.requirement_check.code
                for c in evaluation.check_results.select_related("requirement_check")
                if c.status in ("NAO_ATENDE", "NAO_ENVIADO")
            ]
            _compare(
                row, "analyst", text(record["values"]["analyst"]), evaluation.analyst.first_name
            )
        rows["evaluations"].append(row)
    reviews = {
        r.submission_id: r
        for r in Review.objects.filter(submission__edital=edital).select_related("reviewer")
    }
    source_records = {(r.sheet, r.row): r for r in LegacySourceRecord.objects.filter(run=run)}
    for record in data.reviews:
        row, v = _row(record), record["values"]
        sub = subs.get(record["processo_sei"])
        review = reviews.get(sub.pk) if sub else None
        if review is None:
            row["mismatch_codes"].append("MISSING_REVIEW")
        else:
            _compare(
                row,
                "review_result",
                normalize_review(v["result"]) or "PENDING_DECISION",
                review.preliminary_result,
            )
            _compare(
                row,
                "reviewer",
                text(v["reviewer"]),
                review.reviewer.first_name if review.reviewer else "",
            )
            row["review_result_raw"] = json_value(v["result"])
            row["comparison_kind"] = "IMPORTED_DECISION_NOT_LEGAL_RECOMPUTATION"
        source = source_records.get((record["sheet"], record["row"]))
        _compare(
            row, "raw_provenance_intact", True, bool(source and source.raw_values == record["raw"])
        )
        rows["reviews"].append(row)
    diligence_by_sei = defaultdict(list)
    for record in data.diligences:
        diligence_by_sei[record["processo_sei"]].append(record)
    for sei, records in diligence_by_sei.items():
        row = {"processo_sei": sei, "mismatch_codes": []}
        sub = subs.get(sei)
        events = list(Diligence.objects.filter(submission=sub)) if sub else []
        _compare(row, "event_count", len(records), len(events))
        row["source_rows"] = [r["row"] for r in records]
        row["legacy_statuses"] = [json_value(r["values"]["status"]) for r in records]
        row["legacy_results"] = [json_value(r["values"]["result"]) for r in records]
        row["operational_statuses"] = [e.status for e in events]
        for record in records:
            link = LegacyEntityLink.objects.filter(
                edital=edital,
                source_sha256=data.sha256,
                sheet=record["sheet"],
                row=record["row"],
                entity_type="Diligence",
            ).first()
            event = next((e for e in events if link and e.pk == link.entity_id), None)
            source = source_records.get((record["sheet"], record["row"]))
            if event is None or source is None or source.raw_values != record["raw"]:
                row["mismatch_codes"].append("DILIGENCE_EVENT_PROVENANCE")
            if event and any((event.deadline, event.requested_at, event.requested_by_id)):
                row["mismatch_codes"].append("FABRICATED_HISTORICAL_CONTEXT")
        rows["diligences"].append(row)
    # Historical formula: first absolute CNPJ registration, then initial BY eligibility.
    resolution = DuplicateService.resolve_duplicates(
        subs.values(), edital.duplicate_policy, include_closed=True
    )
    suppressed = {s.processo_sei for s in resolution.suppressed}
    winners = {s.institution.cnpj: s for s in resolution.retained}
    cached_initial = {r["processo_sei"]: text(r["values"]["result"]) for r in data.analyses}
    historical = _positions(
        s
        for s in resolution.retained
        if cached_initial.get(s.processo_sei) == "APTA" and s.target_group != "SEM_GRUPO"
    )
    recalculated = _positions(
        s
        for s in resolution.retained
        if calculated_results.get(s.processo_sei) == "APTA" and s.target_group != "SEM_GRUPO"
    )
    official = (
        {
            e.snapshot_data.get("processo_sei", e.submission.processo_sei): (
                e.target_group,
                e.position,
            )
            for e in snapshot.entries.select_related("submission")
        }
        if snapshot
        else {}
    )
    if snapshot is None:
        incomplete.append("Official RankingService snapshot was not generated for comparison")
    materialized = {
        r["processo_sei"]: (r["block"], int(re.search(r"\d+", text(r["values"]["position"]))[0]))
        for r in data.ranking
    }
    for record in data.distribution:
        row, sei = _row(record), record["processo_sei"]
        _compare(row, "historical_initial_position", materialized.get(sei), historical.get(sei))
        _compare(row, "recalculated_initial_position", materialized.get(sei), recalculated.get(sei))
        if snapshot:
            _compare(row, "official_operational_position", materialized.get(sei), official.get(sei))
        rows["ranking"].append(row)
    consolidated_by_sei = {
        r["processo_sei"]: text(r["values"]["result"])
        for r in data.consolidated
        if r["processo_sei"]
    }
    for record in data.distribution:
        sei, sub = record["processo_sei"], subs.get(record["processo_sei"])
        if sub is None:
            continue
        winner = winners[sub.institution.cnpj]
        rows["reconciliation"].append(
            {
                "processo_sei": sei,
                "cnpj": sub.institution.cnpj,
                "initial_by": cached_initial.get(sei),
                "consolidated_bx": consolidated_by_sei.get(sei),
                "calculated_initial": calculated_results.get(sei),
                "group": sub.target_group,
                "kept_sei": winner.processo_sei,
                "duplicate_suppressed": sei in suppressed,
                "legacy_displayed_position": materialized.get(sei),
                "historical_formula_position": historical.get(sei),
                "official_operational_position": official.get(sei),
                "mismatch_codes": [],
            }
        )
    for sub in resolution.suppressed:
        winner = winners[sub.institution.cnpj]
        rows["duplicates"].append(
            {
                "cnpj": sub.institution.cnpj,
                "kept_sei": winner.processo_sei,
                "suppressed_sei": sub.processo_sei,
                "kept_timestamp": winner.received_at.isoformat(),
                "suppressed_timestamp": sub.received_at.isoformat(),
                "kept_group": winner.target_group,
                "suppressed_group": sub.target_group,
                "kept_initial_result": cached_initial.get(winner.processo_sei),
                "suppressed_initial_result": cached_initial.get(sub.processo_sei),
                "reason": "KEEP_EARLIEST_SUBMISSION_ABSOLUTE",
                "mismatch_codes": [],
            }
        )
    field_codes = Counter(
        code for area in rows.values() for row in area for code in row["mismatch_codes"]
    )
    issues = list(
        LegacyImportIssue.objects.filter(run=run).values(
            "severity", "code", "sheet", "row", "column", "processo_sei", "raw_value"
        )
    )
    error_count = sum(i["severity"] == "ERROR" for i in issues)
    initial_counts = Counter(cached_initial.values())
    metrics_counts = {
        "APTA": data.metrics.get("B4"),
        "INAPTA": data.metrics.get("B3"),
        "EM_ANALISE": data.metrics.get("B5"),
    }
    metric_mismatches = sum(
        initial_counts.get(key.replace("_", " "), 0) != val for key, val in metrics_counts.items()
    )
    by_counts = Counter(text(r["values"]["result"]) for r in data.consolidated)
    summary = {
        "source_sha256": data.sha256,
        "real_workbook_executed": True,
        "status": parity_status(
            True, sum(field_codes.values()) + error_count + metric_mismatches, incomplete
        ),
        "processes_compared": len(data.distribution),
        "sheet_count": len(data.sheets),
        "analyst_sheet_count": sum(s.startswith("ANÁLISE -") for s in data.sheets),
        "analyst_workloads": sorted(Counter(r["sheet"] for r in data.analyses).values()),
        "raw_groups_system": dict(Counter(s.target_group for s in subs.values())),
        "initial_results_excel": dict(initial_counts),
        "initial_results_calculated": dict(Counter(calculated_results.values())),
        "consolidated_results_excel": dict(by_counts),
        "consolidated_rows_without_sei": sum(not r["processo_sei"] for r in data.consolidated),
        "displayed_legacy_metrics": metrics_counts,
        "displayed_group_metrics": {
            result: {
                group: data.metrics.get(f"{column}{line}")
                for group, column in zip(("G1", "G2", "G3", "SEM_GRUPO"), "CDEF", strict=True)
            }
            for result, line in (("INAPTA", 3), ("APTA", 4))
        },
        "review_rows": len(data.reviews),
        "review_cached_results": dict(
            Counter(text(r["values"]["result"]) or "EMPTY" for r in data.reviews)
        ),
        "diligence_rows": len(data.diligences),
        "diligence_unique_seis": len(diligence_by_sei),
        "materialized_ranking_groups": dict(Counter(v[0] for v in materialized.values())),
        "historical_formula_groups": dict(Counter(v[0] for v in historical.values())),
        "recalculated_initial_ranking_groups": dict(Counter(v[0] for v in recalculated.values())),
        "official_operational_ranking_groups": dict(Counter(v[0] for v in official.values())),
        "duplicate_cnpjs": len({s.institution.cnpj for s in resolution.suppressed}),
        "duplicate_excess": len(suppressed),
        "reconciliation": {
            "initial_aptas": initial_counts["APTA"],
            "suppressed_initial_aptas": sum(
                cached_initial.get(sei) == "APTA" for sei in suppressed
            ),
            "no_group_initial_aptas_retained": sum(
                cached_initial.get(s.processo_sei) == "APTA" and s.target_group == "SEM_GRUPO"
                for s in resolution.retained
            ),
            "historical_formula_ranked": len(historical),
            "displayed_ranked": len(materialized),
            "metrics_aptas": data.metrics.get("B4"),
        },
        "mismatches_by_code": dict(field_codes),
        "field_mismatch_count": sum(field_codes.values()),
        "mismatch_count": sum(field_codes.values()) + error_count + metric_mismatches,
        "records_with_mismatches": {
            area: sum(bool(r["mismatch_codes"]) for r in entries) for area, entries in rows.items()
        },
        "source_issue_codes": dict(Counter(i["code"] for i in issues)),
        "source_errors": error_count,
        "metric_mismatch_count": metric_mismatches,
        "incomplete_areas": incomplete,
        "intentional_differences": [
            "New official workflow uses review decisions; Excel CLASSIFICAÇÃO uses initial BY",
            "Financial values rounded to cents with Decimal HALF_UP",
            "No invented historical operational context",
        ],
        "entity_counts": entity_counts(edital),
    }
    return {"summary": summary, "rows": rows, "issues": issues}
