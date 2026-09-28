"""Importador robusto e idempotente para planilhas legadas do Excel Online."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import openpyxl
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Edital, ProgramMunicipality, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.institutions.cnpj import normalize_cnpj
from apps.institutions.models import Institution, Municipality
from apps.ranking.services.classification import ClassificationService
from apps.reviews.models import Diligence, Review
from apps.submissions.models import Assignment, Submission


@dataclass
class LegacyImportReport:
    """Relatório estruturado da execução do importador legado."""

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
    warnings: list[str] = field(default_factory=list)
    skipped_rows: list[str] = field(default_factory=list)


class LegacyImporter:
    """Serviço de importação e auditoria do arquivo Excel legado."""

    def __init__(
        self,
        filepath: str,
        edital_number: str = "1",
        edital_year: int = 2026,
        dry_run: bool = False,
    ):
        self.filepath = filepath
        self.edital_number = edital_number
        self.edital_year = edital_year
        self.dry_run = dry_run
        self.report = LegacyImportReport()

    def run(self) -> LegacyImportReport:
        """Executa a importação completa do arquivo Excel."""
        wb = openpyxl.load_workbook(self.filepath, data_only=True)

        with transaction.atomic():
            edital, _ = Edital.objects.get_or_create(
                number=self.edital_number,
                year=self.edital_year,
                defaults={
                    "name": f"Edital {self.edital_number}/{self.edital_year}",
                    "opens_at": timezone.now() - timezone.timedelta(days=60),
                    "closes_at": timezone.now() + timezone.timedelta(days=30),
                    "rules_version": "1.0",
                },
            )

            # 1. Carrega municípios PRONASCI se houver aba auxiliar
            self._import_pronasci_sheet(wb, edital)

            # 2. Carrega aba DISTRIBUIÇÃO (universo de processos)
            submissions_map = self._import_distribution_sheet(wb, edital)

            # 3. Carrega abas de analistas
            self._import_analyst_sheets(wb, edital, submissions_map)

            # 4. Carrega aba REVISÃO
            self._import_review_sheet(wb, submissions_map)

            # 5. Carrega aba DILIGÊNCIA
            self._import_diligence_sheet(wb, submissions_map)

            # 6. Recalcula classificação final para consolidação de contagens
            self._consolidate_classification_metrics(edital)

            if self.dry_run:
                transaction.set_rollback(True)

        return self.report

    def _import_pronasci_sheet(self, wb: openpyxl.Workbook, edital: Edital):
        sheet_names = [s for s in wb.sheetnames if "PRONASCI" in s.upper()]
        if not sheet_names:
            return

        ws = wb[sheet_names[0]]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            ibge_code = str(row[0]).strip().zfill(7)
            name = str(row[1]).strip() if len(row) > 1 and row[1] else "Município"
            state = str(row[2]).strip().upper() if len(row) > 2 and row[2] else "BR"

            muni, _ = Municipality.objects.get_or_create(
                ibge_code=ibge_code,
                defaults={"name": name, "state": state},
            )
            ProgramMunicipality.objects.get_or_create(
                edital=edital,
                municipality=muni,
                program_name="PRONASCI",
                defaults={"active": True},
            )

    def _import_distribution_sheet(
        self, wb: openpyxl.Workbook, edital: Edital
    ) -> dict[str, Submission]:
        sheet_names = [s for s in wb.sheetnames if "DISTRIBUI" in s.upper()]
        if not sheet_names:
            self.report.warnings.append("Aba DISTRIBUIÇÃO não encontrada no arquivo.")
            return {}

        ws = wb[sheet_names[0]]
        submissions_map: dict[str, Submission] = {}

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(row):
                continue
            sei = str(row[0]).strip() if row[0] else ""
            if not sei:
                self.report.skipped_rows.append(f"Linha {row_idx}: Processo SEI vazio.")
                continue

            self.report.total_rows_read += 1

            # Data/Hora Protocolo
            raw_dt = row[1] if len(row) > 1 else None
            received_at = self._parse_datetime(raw_dt)

            # CNPJ e Razão Social
            raw_cnpj = str(row[2]).strip() if len(row) > 2 and row[2] else f"{row_idx:014d}"
            cnpj_clean = normalize_cnpj(raw_cnpj)
            if not cnpj_clean:
                cnpj_clean = f"{row_idx:014d}"

            razao_social = str(row[3]).strip() if len(row) > 3 and row[3] else f"Entidade {sei}"

            # Município e UF
            muni_name = str(row[4]).strip() if len(row) > 4 and row[4] else ""
            uf = str(row[5]).strip().upper() if len(row) > 5 and row[5] else ""
            municipality = None
            if muni_name and uf:
                municipality = Municipality.objects.filter(
                    name__iexact=muni_name, state__iexact=uf
                ).first()
                if not municipality:
                    # Gera um código IBGE fictício se não cadastrado previamente
                    fictitious_code = f"99{abs(hash((muni_name, uf))) % 100000:05d}"
                    municipality, _ = Municipality.objects.get_or_create(
                        ibge_code=fictitious_code,
                        defaults={"name": muni_name, "state": uf},
                    )

            # Vagas e Capacidade
            fem = (
                int(row[6]) if len(row) > 6 and row[6] is not None and str(row[6]).isdigit() else 0
            )
            masc = (
                int(row[7]) if len(row) > 7 and row[7] is not None and str(row[7]).isdigit() else 0
            )
            nutrizes = (
                int(row[8]) if len(row) > 8 and row[8] is not None and str(row[8]).isdigit() else 0
            )
            solicitadas = (
                int(row[9])
                if len(row) > 9 and row[9] is not None and str(row[9]).isdigit()
                else (fem + masc + nutrizes)
            )
            capacidade = (
                int(row[10])
                if len(row) > 10 and row[10] is not None and str(row[10]).isdigit()
                else solicitadas
            )

            analyst_name = str(row[11]).strip() if len(row) > 11 and row[11] else ""
            status_txt = str(row[12]).strip().upper() if len(row) > 12 and row[12] else "EM_ANALISE"

            # Criação da Instituição
            institution, _ = Institution.objects.get_or_create(
                cnpj=cnpj_clean,
                defaults={"name": razao_social, "municipality": municipality},
            )

            # Mapeamento do WorkflowStatus
            wf_status = Submission.WorkflowStatus.RECEIVED
            if analyst_name:
                wf_status = Submission.WorkflowStatus.ASSIGNED
            if status_txt == "APTA":
                wf_status = Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
            elif status_txt == "INAPTA":
                wf_status = Submission.WorkflowStatus.INELIGIBLE

            # Persistência da Submissão (Idempotente)
            submission, created = Submission.objects.update_or_create(
                edital=edital,
                processo_sei=sei,
                defaults={
                    "institution": institution,
                    "municipality": municipality,
                    "received_at": received_at,
                    "vagas_femininas": fem,
                    "vagas_masculinas": masc,
                    "vagas_maes_nutrizes": nutrizes,
                    "vagas_solicitadas": solicitadas,
                    "capacidade_total": capacidade,
                    "workflow_status": wf_status,
                },
            )

            if created:
                self.report.submissions_created += 1
                AuditEvent.objects.create(
                    actor=None,
                    action="CREATE",
                    entity_type="Submission",
                    entity_id=str(submission.id),
                    metadata={"source": "legacy_excel_import", "row": row_idx},
                )
            else:
                self.report.submissions_updated += 1

            # Atribuição ao analista
            if analyst_name:
                analyst_user = self._get_or_create_analyst(analyst_name)
                distributor = self._get_or_create_user("sistema.legado", User.Role.DISTRIBUIDOR)
                assignment, assign_created = Assignment.objects.get_or_create(
                    submission=submission,
                    analyst=analyst_user,
                    defaults={
                        "status": Assignment.Status.ACTIVE,
                        "assigned_by": distributor,
                    },
                )
                if assign_created:
                    self.report.assignments_created += 1

            # Classifica o grupo de enquadramento
            ClassificationService.classify_and_update(submission)
            submissions_map[sei] = submission

        return submissions_map

    def _import_analyst_sheets(
        self,
        wb: openpyxl.Workbook,
        edital: Edital,
        submissions_map: dict[str, Submission],
    ):
        ignored_sheets = {
            "DISTRIBUIÇÃO",
            "DISTRIBUICAO",
            "REVISÃO",
            "REVISAO",
            "DILIGÊNCIA",
            "DILIGENCIA",
            "CLASSIFICAÇÃO",
            "CLASSIFICACAO",
            "MÉTRICAS",
            "METRICAS",
            "AUX_PRONASCI",
            "PRONASCI",
            "AUXILIARES",
        }

        analyst_sheets = [s for s in wb.sheetnames if s.strip().upper() not in ignored_sheets]

        for s_name in analyst_sheets:
            ws = wb[s_name]
            analyst_user = self._get_or_create_analyst(s_name)

            headers = [
                c for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True), []) if c
            ]
            if not headers:
                continue

            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[0]:
                    continue
                sei = str(row[0]).strip()
                submission = submissions_map.get(sei)
                if not submission:
                    continue

                # Cria avaliação
                evaluation, _ = Evaluation.objects.get_or_create(
                    submission=submission,
                    defaults={
                        "analyst": analyst_user,
                        "status": Evaluation.Status.COMPLETED,
                        "result": Evaluation.Result.APTA,
                    },
                )
                self.report.evaluations_created += 1

                # Requisitos nas colunas
                for col_idx, col_name in enumerate(headers[1:], start=1):
                    if col_idx >= len(row):
                        break
                    val = str(row[col_idx]).strip().upper() if row[col_idx] is not None else ""
                    if not val or col_name.upper() in ["PARECER FINAL", "OBSERVAÇÕES", "STATUS"]:
                        continue

                    req_code = str(col_name).strip()
                    req, _ = Requirement.objects.get_or_create(
                        edital=edital,
                        code=req_code,
                        defaults={
                            "name": f"Requisito {req_code}",
                            "mandatory": True,
                            "order": col_idx,
                        },
                    )
                    check, _ = RequirementCheck.objects.get_or_create(
                        requirement=req,
                        name=f"Critério {req_code}",
                        defaults={"order": 1},
                    )

                    status = CheckResult.Status.ATENDE
                    if "NÃO ATENDE" in val or "NAO ATENDE" in val:
                        status = CheckResult.Status.NAO_ATENDE
                    elif "NÃO ENVIADO" in val or "NAO ENVIADO" in val:
                        status = CheckResult.Status.NAO_ENVIADO
                    elif "N/A" in val or "INAPLICAVEL" in val:
                        status = CheckResult.Status.NAO_APLICAVEL

                    CheckResult.objects.update_or_create(
                        evaluation=evaluation,
                        requirement_check=check,
                        defaults={"status": status},
                    )

    def _import_review_sheet(self, wb: openpyxl.Workbook, submissions_map: dict[str, Submission]):
        sheet_names = [s for s in wb.sheetnames if "REVIS" in s.upper()]
        if not sheet_names:
            return

        ws = wb[sheet_names[0]]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            sei = str(row[0]).strip()
            sub = submissions_map.get(sei)
            if not sub:
                continue

            rev_name = str(row[1]).strip() if len(row) > 1 and row[1] else "REVISOR"
            reviewer_user = self._get_or_create_user(rev_name, User.Role.REVISOR)

            evaluation = getattr(sub, "evaluation", None)
            if not evaluation:
                evaluation, _ = Evaluation.objects.get_or_create(
                    submission=sub,
                    defaults={
                        "analyst": reviewer_user,
                        "status": Evaluation.Status.COMPLETED,
                        "result": Evaluation.Result.APTA,
                    },
                )

            Review.objects.update_or_create(
                evaluation=evaluation,
                defaults={
                    "submission": sub,
                    "reviewer": reviewer_user,
                    "status": Review.Status.COMPLETED,
                    "preliminary_result": Review.PreliminaryResult.PRE_HABILITADO,
                    "decision_notes": str(row[4]).strip()
                    if len(row) > 4 and row[4]
                    else "Revisão efetuada",
                },
            )
            self.report.reviews_created += 1

    def _import_diligence_sheet(
        self, wb: openpyxl.Workbook, submissions_map: dict[str, Submission]
    ):
        sheet_names = [s for s in wb.sheetnames if "DILIG" in s.upper()]
        if not sheet_names:
            return

        ws = wb[sheet_names[0]]
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = self._get_or_create_user("admin", User.Role.ADMINISTRADOR)

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            sei = str(row[0]).strip()
            sub = submissions_map.get(sei)
            if not sub:
                continue

            reason = (
                str(row[1]).strip() if len(row) > 1 and row[1] else "Esclarecimentos complementares"
            )
            deadline = timezone.now().date() + timezone.timedelta(days=15)

            Diligence.objects.update_or_create(
                submission=sub,
                reason=reason,
                defaults={
                    "requested_by": admin_user,
                    "requested_at": timezone.now(),
                    "deadline": deadline,
                    "status": Diligence.Status.OPEN,
                },
            )
            self.report.diligences_created += 1

    def _consolidate_classification_metrics(self, edital: Edital):
        subs = Submission.objects.filter(edital=edital)
        self.report.g1_count = subs.filter(target_group=Submission.TargetGroup.G1).count()
        self.report.g2_count = subs.filter(target_group=Submission.TargetGroup.G2).count()
        self.report.g3_count = subs.filter(target_group=Submission.TargetGroup.G3).count()
        self.report.sem_grupo_count = subs.filter(
            target_group=Submission.TargetGroup.SEM_GRUPO
        ).count()

    def _get_or_create_analyst(self, name: str) -> User:
        return self._get_or_create_user(name, User.Role.ANALISTA)

    def _get_or_create_user(self, name: str, role: str) -> User:
        username = slugify(name).replace("-", ".") or "analista"
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@mds.gov.br",
                "first_name": name,
                "role": role,
            },
        )
        return user

    def _parse_datetime(self, val: Any) -> datetime:
        if isinstance(val, datetime):
            return timezone.make_aware(val) if timezone.is_naive(val) else val
        if val:
            try:
                dt = datetime.strptime(str(val), "%Y-%m-%d %H:%M:%S")
                return timezone.make_aware(dt)
            except Exception:
                pass
        return timezone.now()
