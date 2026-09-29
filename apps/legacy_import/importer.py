"""Import real historical rows with explicit provenance and no fabricated identities."""

from collections import Counter
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Edital, ProgramMunicipality, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.evaluations.services.evaluation import EvaluationService
from apps.institutions.cnpj import normalize_cnpj, validate_cnpj
from apps.institutions.models import Institution, Municipality
from apps.ranking.services.classification import ClassificationService
from apps.reviews.models import Diligence, Review
from apps.submissions.models import Assignment, Submission

from .models import LegacyEntityLink, LegacyImportIssue, LegacyImportRun, LegacySourceRecord
from .normalizers import (
    decimal_value,
    json_value,
    normalize_review,
    normalize_status,
    normalized_text,
    parse_timestamp,
    text,
)
from .parser import parse_workbook
from .schema import CHECKS


@dataclass
class LegacyImportReport:
    run_id: int | None = None
    total_rows_read: int = 0
    submissions_created: int = 0
    submissions_updated: int = 0
    assignments_created: int = 0
    evaluations_created: int = 0
    reviews_created: int = 0
    diligences_created: int = 0
    g1_count: int = 0
    g2_count: int = 0
    g3_count: int = 0
    sem_grupo_count: int = 0
    warnings: list = field(default_factory=list)
    skipped_rows: list = field(default_factory=list)


class LegacyImporter:
    def __init__(self, filepath, edital_number="1", edital_year=2026, dry_run=False, strict=True):
        self.filepath, self.number, self.year = filepath, edital_number, edital_year
        self.dry_run, self.strict = dry_run, strict
        self.report = LegacyImportReport()

    def issue(self, record, code, message, column="", severity="ERROR", raw=None):
        self.issues.append(
            {
                "severity": severity,
                "sheet": record["sheet"],
                "row": record["row"],
                "column": column,
                "processo_sei": record["processo_sei"],
                "code": code,
                "message": message,
                "raw_value": json_value(raw),
            }
        )

    def provenance(self, record, **entities):
        LegacySourceRecord.objects.create(
            run=self.run_record,
            sheet=record["sheet"],
            row=record["row"],
            processo_sei=record["processo_sei"],
            raw_values=record["raw"],
            formulas=record["formulas"],
            entities={key: value.pk for key, value in entities.items() if value is not None},
        )

    def user(self, name, role):
        if not text(name):
            return None
        user, created = User.objects.get_or_create(
            username="legacy." + slugify(normalized_text(name)),
            defaults={"first_name": text(name),
                "email": None, "role": role, "is_active": False},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user

    def event(self, entity, action):
        AuditEvent.objects.create(
            entity_type=type(entity).__name__,
            entity_id=str(entity.pk),
            action=action,
            metadata={"import_run": self.run_record.pk},
        )

    def run(self):
        data = self.data = parse_workbook(self.filepath)
        self.issues = list(data.issues)
        self.report.total_rows_read = len(data.distribution)
        self.run_record = LegacyImportRun.objects.create(
            source_filename=data.filename,
            source_sha256=data.sha256,
            mode="strict" if self.strict else "lenient",
            total_rows=len(data.distribution),
        )
        self.report.run_id = self.run_record.pk
        failed = False
        try:
            with transaction.atomic():
                timestamps = []
                for record in data.distribution:
                    try:
                        timestamps.append(
                            parse_timestamp(
                                record["values"]["date"], record["values"]["time"], data.epoch
                            )
                        )
                    except (ValueError, TypeError, OverflowError):
                        pass
                if not timestamps:
                    self.issue(
                        {"sheet": "DISTRIBUIÇÃO", "row": 3, "processo_sei": ""},
                        "NO_VALID_TIMESTAMPS",
                        "No historical dates available",
                    )
                    raise ValidationError("No historical dates available")
                edital, _ = Edital.objects.get_or_create(
                    number=self.number,
                    year=self.year,
                    defaults={
                        "name": f"Edital {self.number}/{self.year}",
                        "opens_at": min(timestamps),
                        "closes_at": max(timestamps),
                        "status": Edital.Status.ARCHIVED,
                    },
                )
                self.edital = edital
                names = {}
                for rec in [*data.analyses, *data.reviews, *data.ranking]:
                    name = text(rec["values"].get("institution"))
                    if name:
                        names[rec["processo_sei"]] = name
                        names[normalize_cnpj(rec["values"].get("cnpj"))] = name
                subs = {}
                for rec in data.distribution:
                    sub = self.import_submission(rec, names)
                    if sub:
                        if sub.processo_sei in subs:
                            self.issue(
                                rec,
                                "DUPLICATE_SOURCE_SEI",
                                "Multiple distribution rows share SEI",
                                "E",
                            )
                        subs[sub.processo_sei] = sub
                for rec in data.analyses:
                    self.import_analysis(rec, subs)
                for rec in data.reviews:
                    self.import_review(rec, subs)
                for rec in data.diligences:
                    self.import_diligence(rec, subs)
                counts = Counter(s.target_group for s in subs.values())
                for group, attr in [
                    ("G1", "g1_count"),
                    ("G2", "g2_count"),
                    ("G3", "g3_count"),
                    ("SEM_GRUPO", "sem_grupo_count"),
                ]:
                    setattr(self.report, attr, counts[group])
                if self.strict and any(i["severity"] == "ERROR" for i in self.issues):
                    raise ValidationError("Strict import rejected source issues")
                if self.dry_run:
                    transaction.set_rollback(True)
        except ValidationError:
            failed = True
        self.run_record.edital = Edital.objects.filter(number=self.number, year=self.year).first()
        self.run_record.warning_count = sum(i["severity"] == "WARNING" for i in self.issues)
        self.run_record.error_count = sum(i["severity"] == "ERROR" for i in self.issues)
        self.run_record.status = (
            "FAILED"
            if failed
            else "DRY_RUN"
            if self.dry_run
            else "PARTIAL"
            if self.run_record.error_count
            else "IMPORTED"
        )
        self.run_record.finished_at = timezone.now()
        self.run_record.save()
        LegacyImportIssue.objects.bulk_create(
            [LegacyImportIssue(run=self.run_record, **i) for i in self.issues]
        )
        self.report.warnings = [
            f"{i['code']} {i['sheet']}:{i['row']}:{i['column']}" for i in self.issues
        ]
        if failed:
            raise ValidationError(
                f"Import run {self.run_record.pk} failed; structured issues retained"
            )
        return self.report

    def import_submission(self, rec, names):
        v, sei = rec["values"], rec["processo_sei"]
        cnpj = normalize_cnpj(v["cnpj"])
        if not sei or len(cnpj) != 14:
            self.issue(
                rec, "INVALID_IDENTITY", "Missing/malformed SEI or CNPJ", "E/D", raw=v["cnpj"]
            )
            self.provenance(rec)
            return None
        if not validate_cnpj(cnpj):
            self.issue(
                rec,
                "INVALID_CNPJ",
                "Historical CNPJ checksum invalid; original retained in lenient mode",
                "D",
                raw=v["cnpj"],
            )
        try:
            timestamp = parse_timestamp(v["date"], v["time"], self.data.epoch)
        except (ValueError, TypeError, OverflowError):
            self.issue(
                rec,
                "INVALID_TIMESTAMP",
                "F/G invalid; no invented timestamp",
                "F/G",
                raw=f"{v['date']} {v['time']}",
            )
            self.provenance(rec)
            return None
        name = text(v["institution"]) or names.get(sei) or names.get(cnpj) or ""
        if not name:
            self.issue(
                rec,
                "MISSING_INSTITUTION_NAME",
                "Lookup cache and recovery unavailable",
                "C",
                "WARNING",
            )
        municipality = None
        muni_name, state = text(v["municipality"]), text(v["state"]).upper()
        if muni_name and len(state) == 2:
            municipality = Municipality.objects.filter(name__iexact=muni_name, state=state).first()
            if municipality is None:
                municipality = Municipality.objects.create(
                    name=muni_name, state=state, ibge_code=None
                )
            pronasci_names = {normalized_text(n): n for n in self.data.pronasci}
            if normalized_text(muni_name) in pronasci_names:
                ProgramMunicipality.objects.get_or_create(
                    edital=self.edital,
                    municipality=municipality,
                    program_name="PRONASCI",
                    defaults={"legacy_original_name": pronasci_names[normalized_text(muni_name)]},
                )
        else:
            self.issue(
                rec,
                "MISSING_MUNICIPALITY",
                "Municipality/UF not resolved",
                "M",
                "WARNING",
                muni_name,
            )
        institution, _ = Institution.objects.get_or_create(
            cnpj=cnpj, defaults={"name": name, "municipality": municipality}
        )
        numbers = {}
        for key in [
            "vagas_femininas",
            "vagas_masculinas",
            "vagas_maes_nutrizes",
            "vagas_solicitadas",
            "capacidade_total",
        ]:
            value = decimal_value(v[key]) if v[key] not in (None, "") else 0
            if value is None or value < 0 or int(value) != value:
                self.issue(
                    rec, "INVALID_VACANCIES", "Invalid number; row not imported", key, raw=v[key]
                )
                self.provenance(rec, Institution=institution, Municipality=municipality)
                return None
            numbers[key] = int(value)
        defaults = {
            "institution": institution,
            "municipality": municipality,
            "received_at": timestamp,
            **numbers,
            "valor_global": decimal_value(v["valor_global"]),
            "patrimonio_minimo": decimal_value(v["patrimonio_minimo"]),
        }
        sub, created = Submission.objects.get_or_create(
            edital=self.edital, processo_sei=sei, defaults=defaults
        )
        if not created:
            for key, expected in defaults.items():
                if getattr(sub, key) != expected and key not in (
                    "valor_global",
                    "patrimonio_minimo",
                ):
                    self.issue(
                        rec,
                        "DOMAIN_SOURCE_CONFLICT",
                        f"Existing {key} differs; no silent overwrite",
                        key,
                        raw=v.get(key),
                    )
        self.report.submissions_created += int(created)
        self.report.submissions_updated += int(not created)
        analyst = self.user(v["analyst"], User.Role.ANALISTA)
        assignment = None
        if analyst:
            assignment, assigned = Assignment.objects.get_or_create(
                submission=sub,
                status=Assignment.Status.ACTIVE,
                defaults={"analyst": analyst, "assigned_by": None},
            )
            if assignment.analyst_id != analyst.pk:
                self.issue(
                    rec, "ASSIGNMENT_CONFLICT", "No silent reassignment", "I", raw=v["analyst"]
                )
            self.report.assignments_created += int(assigned)
            if assigned:
                self.event(assignment, "LEGACY_ASSIGNMENT_IMPORTED")
        ClassificationService.classify_and_update(sub)
        if created:
            self.event(sub, "LEGACY_SUBMISSION_IMPORTED")
        self.provenance(
            rec,
            Submission=sub,
            Institution=institution,
            Municipality=municipality,
            Assignment=assignment,
            User=analyst,
        )
        return sub

    def import_analysis(self, rec, subs):
        sub = subs.get(rec["processo_sei"])
        if not sub:
            self.issue(rec, "ORPHAN_ANALYSIS", "No safe distribution identity")
            self.provenance(rec)
            return
        v = rec["values"]
        analyst = self.user(
            v["analyst"] or rec["sheet"].removeprefix("ANÁLISE -").strip(), User.Role.ANALISTA
        )
        evaluation, created = Evaluation.objects.get_or_create(
            submission=sub, defaults={"analyst": analyst}
        )
        if created:
            for order, (code, (columns, evidence)) in enumerate(CHECKS.items(), 1):
                req, _ = Requirement.objects.get_or_create(
                    edital=self.edital, code=code, defaults={"name": code, "order": order}
                )
                for index, col in enumerate(columns, 1):
                    check, _ = RequirementCheck.objects.get_or_create(
                        requirement=req,
                        code=f"{code}-{col}",
                        defaults={
                            "name": col,
                            "order": index,
                            "accepted_statuses": ["ATENDE", "NAO_APLICAVEL"]
                            if col == "BV"
                            else ["ATENDE"],
                            "failure_statuses": ["NAO_ENVIADO"]
                            if col == "BV"
                            else ["NAO_ATENDE", "NAO_ENVIADO"],
                            "contributes_to_result": col != "AW",
                        },
                    )
                    status = normalize_status(v[col], col)
                    if status is None:
                        self.issue(
                            rec,
                            "UNKNOWN_CHECK_STATUS",
                            "Unknown status retained as unevaluated",
                            col,
                            raw=v[col],
                        )
                        status = CheckResult.Status.EM_BRANCO
                    attrs = {}
                    for attr, source in evidence.items():
                        val = v[source]
                        if attr == "minimum_equity":
                            continue
                        if attr == "valid_until":
                            val = val.date() if hasattr(val, "date") else val
                            if not hasattr(val, "year"):
                                if val:
                                    self.issue(
                                        rec,
                                        "INVALID_DOCUMENT_DATE",
                                        "Unparsed date retained in provenance",
                                        source,
                                        "WARNING",
                                        val,
                                    )
                                val = None
                        else:
                            val = text(val)
                        attrs[attr] = val
                    CheckResult.objects.create(
                        evaluation=evaluation,
                        requirement_check=check,
                        status=status,
                        legacy_raw_value=json_value(v[col]),
                        **attrs,
                    )
            assessment = EvaluationService.calculate_assessment(evaluation)
            evaluation.result = assessment.result
            evaluation.failed_requirement_codes = assessment.failed_requirement_codes
            evaluation.status = (
                Evaluation.Status.COMPLETED
                if text(v["result"]) in ("APTA", "INAPTA")
                else Evaluation.Status.DRAFT
            )
            evaluation.save()
            self.report.evaluations_created += 1
            self.event(evaluation, "LEGACY_EVALUATION_IMPORTED")
            self.legacy_workflow(
                sub,
                Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
                if assessment.result == "APTA"
                else Submission.WorkflowStatus.PENDING_REVIEW
                if assessment.result == "INAPTA"
                else Submission.WorkflowStatus.UNDER_ANALYSIS,
            )
        self.provenance(rec, Evaluation=evaluation)

    def legacy_workflow(self, sub, target):
        if sub.workflow_status == target:
            return
        previous = sub.workflow_status
        sub.workflow_status = target
        sub.save(update_fields=["workflow_status", "updated_at"])
        AuditEvent.objects.create(
            entity_type="Submission",
            entity_id=str(sub.pk),
            action="LEGACY_WORKFLOW_RECONSTRUCTED",
            field="workflow_status",
            old_value=previous,
            new_value=target,
            metadata={"import_run": self.run_record.pk},
        )

    def import_review(self, rec, subs):
        sub = subs.get(rec["processo_sei"])
        evaluation = Evaluation.objects.filter(submission=sub).first() if sub else None
        if not evaluation:
            self.issue(rec, "ORPHAN_REVIEW", "No evaluation; no artificial analysis created")
            self.provenance(rec)
            return
        v = rec["values"]
        result = normalize_review(v["result"])
        if v["result"] and result is None:
            self.issue(
                rec,
                "UNKNOWN_REVIEW_RESULT",
                "Unknown result preserved without decision",
                "CG",
                raw=v["result"],
            )
        reviewer = self.user(v["reviewer"], User.Role.REVISOR)
        review, created = Review.objects.get_or_create(
            evaluation=evaluation,
            defaults={
                "submission": sub,
                "reviewer": reviewer,
                "status": Review.Status.COMPLETED if result else Review.Status.PENDING,
                "preliminary_result": result or Review.PreliminaryResult.PENDING_DECISION,
                "decision_notes": text(v["notes"]),
            },
        )
        self.report.reviews_created += int(created)
        if created:
            self.event(review, "LEGACY_REVIEW_IMPORTED")
            self.legacy_workflow(
                sub,
                Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
                if result == "PRE_HABILITADO"
                else Submission.WorkflowStatus.INELIGIBLE
                if result
                else Submission.WorkflowStatus.PENDING_REVIEW,
            )
        self.provenance(rec, Review=review, User=reviewer)

    def import_diligence(self, rec, subs):
        sub = subs.get(rec["processo_sei"])
        if not sub:
            self.issue(rec, "ORPHAN_DILIGENCE", "No safe distribution identity")
            self.provenance(rec)
            return
        key = {
            "edital": self.edital,
            "source_sha256": self.data.sha256,
            "sheet": rec["sheet"],
            "row": rec["row"],
            "entity_type": "Diligence",
        }
        link = LegacyEntityLink.objects.filter(**key).first()
        if link:
            diligence = Diligence.objects.get(pk=link.entity_id)
        else:
            diligence = Diligence.objects.create(
                submission=sub,
                requested_by=None,
                requested_at=None,
                deadline=None,
                status=Diligence.Status.LEGACY_UNKNOWN,
                reason=text(rec["values"]["reason"]),
                result=Diligence.Result.PENDENTE,
            )
            LegacyEntityLink.objects.create(**key, entity_id=diligence.pk)
            self.report.diligences_created += 1
            self.event(diligence, "LEGACY_DILIGENCE_IMPORTED")
        self.provenance(rec, Diligence=diligence)
