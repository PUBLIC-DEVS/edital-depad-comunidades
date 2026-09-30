"""Explicit LOCAL DEVELOPMENT ONLY dataset; never called by startup/entrypoints."""

from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.edital_2026 import configure_edital_2026_base
from apps.editais.models import Edital, ProgramMunicipality
from apps.editais.services import EditalConfigurationService
from apps.evaluations.services import EvaluationService
from apps.institutions.models import Institution, Municipality
from apps.ranking.services import ClassificationService, RankingService
from apps.reviews.services import ReviewService
from apps.submissions.models import Submission
from apps.submissions.services.workflow import WorkflowService

DATASET_NUMBER = "HOMOLOG-LOCAL"
DATASET_VERSION = "2026-v1"
LOCAL_PASSWORD = "Homolog.Edital#2026"  # Synthetic, LOCAL DEVELOPMENT ONLY.
ROLES = {
    "admin": User.Role.ADMINISTRADOR,
    "coordenador": User.Role.COORDENADOR,
    "distribuidor": User.Role.DISTRIBUIDOR,
    "analista": User.Role.ANALISTA,
    "revisor": User.Role.REVISOR,
    "consulta": User.Role.CONSULTA,
}
# Generated test identifiers, with valid check digits; no institution registry lookup.
SYNTHETIC_CNPJS = (
    "HOMOLOG0000104",
    "HOMOLOG0000295",
    "HOMOLOG0000376",
    "HOMOLOG0000457",
    "HOMOLOG0000538",
    "HOMOLOG0000619",
    "HOMOLOG0000708",
    "HOMOLOG0000880",
)
SCENARIOS = (
    ("Sem distribuição", "G1", "received"),
    ("Análise parcial 17 de 23", "G2", "partial"),
    ("Análise nova", "G3", "new"),
    ("Revisão pendente", "G1", "review"),
    ("Apta G1", "G1", "apt"),
    ("Inapta final", "G2", "inapt"),
    ("Apta G2", "G2", "apt"),
    ("Apta G3", "G3", "apt"),
)
FAILED_CODES = {"SEM_REMUNERACAO", "REGULARIDADE_SICAF", "LICENCA_SANITARIA"}


class Command(BaseCommand):
    help = "LOCAL DEVELOPMENT ONLY: cria homologação sintética 2026, sem Excel e sem reset."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or settings.AUTH_ADAPTER != "local":
            raise CommandError(
                "Somente desenvolvimento local: requer DEBUG=True e AUTH_ADAPTER=local."
            )
        existing = Edital.objects.filter(number=DATASET_NUMBER, year=2026).first()
        if (
            Edital.objects.filter(status=Edital.Status.ACTIVE)
            .exclude(pk=existing.pk if existing else None)
            .exists()
        ):
            raise CommandError(
                "Outro edital ACTIVE já existe. Use um banco local de homologação separado. "
                "Nenhum dado foi alterado; este comando não desativa editais nem apaga volumes."
            )
        if existing:
            marker = AuditEvent.objects.filter(
                entity_type="Edital",
                entity_id=str(existing.pk),
                action="HOMOLOGATION_SEED",
                metadata__dataset_version=DATASET_VERSION,
            ).exists()
            if not marker or existing.status != Edital.Status.ACTIVE:
                raise CommandError(
                    "Dataset existente incompleto ou não ativo. Nenhum dado foi alterado."
                )
            self.stdout.write("Homologação já existente; decisões, senhas e histórico preservados.")
            self.print_access()
            return
        usernames = [f"homolog.{key}" for key in ROLES]
        if User.objects.filter(username__in=usernames).exists():
            raise CommandError(
                "Contas homolog.* já existem sem este dataset. Nenhuma conta foi sobrescrita."
            )
        users = {
            key: User.objects.create_user(
                username=f"homolog.{key}",
                password=LOCAL_PASSWORD,
                role=role,
                first_name=f"Homologação {key.title()}",
                email=f"{key}@homolog.example",
            )
            for key, role in ROLES.items()
        }
        admin = users["admin"]
        now = timezone.now()
        edital = EditalConfigurationService.save(
            Edital(
                number=DATASET_NUMBER,
                year=2026,
                name="EDITAL 2026 — HOMOLOGAÇÃO LOCAL (SINTÉTICO)",
                opens_at=now - timedelta(days=30),
                closes_at=now + timedelta(days=365),
                rules_version=DATASET_VERSION,
                validation_reference_date=now.date(),
                requires_financial_rules=False,
                tie_breaker_policy="SEI_LEXICOGRAPHIC",
            ),
            admin,
        )
        configure_edital_2026_base(edital, admin)
        municipalities = {
            code: Municipality.objects.get_or_create(
                name=f"Município sintético de homologação {code}",
                state="DF",
                ibge_code=None,
            )[0]
            for code in ("A", "B")
        }
        # This fictional program link exercises G2; it is not an official PRONASCI list.
        EditalConfigurationService.save(
            ProgramMunicipality(
                edital=edital,
                program=edital.target_groups.get(code="G2").program,
                program_name="PRONASCI",
                municipality=municipalities["A"],
            ),
            admin,
        )
        EditalConfigurationService.publish(edital, admin)
        edital.refresh_from_db()
        for index, (label, group, scenario) in enumerate(SCENARIOS, 1):
            municipality = municipalities["B" if group == "G3" else "A"]
            institution = Institution(
                name=f"HOMOLOGAÇÃO {index:02} — {label} (fictícia)",
                cnpj=SYNTHETIC_CNPJS[index - 1],
                municipality=municipality,
                address="Rua de teste, sem endereço real",
                postal_code="00000-000",
            )
            institution.full_clean()
            institution.save()
            submission = Submission.objects.create(
                edital=edital,
                institution=institution,
                municipality=municipality,
                processo_sei=f"HOMOLOG-2026-{index:03}",
                received_at=now - timedelta(days=10 - index),
                vagas_femininas=10 if group == "G1" else 0,
                vagas_masculinas=10 if group != "G1" else 0,
                vagas_solicitadas=10,
                capacidade_total=20,
            )
            ClassificationService.classify_and_update(submission, admin)
            if submission.target_group != group:
                raise CommandError(
                    "Configuração-base não produziu o grupo esperado; seed revertido."
                )
            if scenario != "received":
                self.prepare_analysis(submission, scenario, users, now)
        RankingService.generate_snapshot(
            edital,
            users["coordenador"],
            description="Homologação local — resultados sintéticos",
        )
        AuditEvent.objects.create(
            actor=admin,
            entity_type="Edital",
            entity_id=str(edital.pk),
            action="HOMOLOGATION_SEED",
            metadata={"dataset_version": DATASET_VERSION},
        )
        self.stdout.write(
            self.style.SUCCESS("Homologação criada: 8 processos, 14 blocos, 23 critérios.")
        )
        self.print_access()

    def prepare_analysis(self, submission, scenario, users, now):
        analyst = users["analista"]
        WorkflowService.assign_analyst(submission, analyst, users["distribuidor"])
        evaluation = EvaluationService.start_evaluation(submission, analyst)
        if scenario == "new":
            return
        checks = list(
            evaluation.check_results.select_related("requirement_check").order_by(
                "requirement__order",
                "requirement_check__order",
            )
        )
        if scenario == "partial":
            checks = checks[:17]  # Dataset example, never a runtime completion rule.
        payloads = []
        for result in checks:
            definition = result.definition
            status = (
                "NAO_ATENDE"
                if scenario in {"review", "inapt"} and definition.code in FAILED_CODES
                else "ATENDE"
            )
            if definition.code == "COMPROVACAO_AUTODECLARADA":
                status = "NAO_APLICAVEL"
            evidence = {
                "document_cnpj": submission.institution.cnpj,
                "canonical_cnpj_confirmed": True,
                "valid_until": now.date() + timedelta(days=365),
                "opened_on": date(now.year - 5, 1, 1),
                "cnae": "87.20-4-99",
                "notes": "Conferência sintética para homologação local.",
            }
            payloads.append(
                {
                    "check_result_id": result.pk,
                    "status": status,
                    **{
                        name: value
                        for name, value in evidence.items()
                        if name in definition.evidence_fields
                    },
                }
            )
        EvaluationService.save_draft(evaluation, payloads, analyst)
        if scenario == "partial":
            return
        EvaluationService.conclude_evaluation(evaluation, analyst)
        if scenario == "inapt":
            review = ReviewService.claim_review(evaluation.review, users["revisor"])
            for result in EvaluationService.blocking_check_results(evaluation):
                ReviewService.record_effective_status(
                    review,
                    result.pk,
                    result.status,
                    "Falha confirmada no exemplo sintético.",
                    users["revisor"],
                )
            ReviewService.conclude_review(
                review,
                actor=users["revisor"],
                decision_notes="INAPTA — homologação sintética.",
            )

    def print_access(self):
        self.stdout.write("LOCAL DEVELOPMENT ONLY — http://localhost:8000/")
        self.stdout.write("Usuários: " + ", ".join(f"homolog.{key}" for key in ROLES))
        self.stdout.write(
            f"Senha inicial local: {LOCAL_PASSWORD} (não é redefinida em reexecuções)."
        )
