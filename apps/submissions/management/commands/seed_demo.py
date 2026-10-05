"""A new configurable edital, created without importing or opening any workbook."""

import os
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import (
    ClassificationPolicy,
    Edital,
    FundingRule,
    Program,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
    TargetGroup,
)
from apps.editais.services import EditalConfigurationService
from apps.evaluations.services import EvaluationService
from apps.institutions.models import Institution, Municipality
from apps.ranking.services import ClassificationService, RankingService
from apps.reviews.models import Review
from apps.reviews.services import ReviewService
from apps.submissions.models import Submission
from apps.submissions.services.funding import FundingService
from apps.submissions.services.workflow import WorkflowService


class Command(BaseCommand):
    help = "Cria demonstração operacional configurável sem Excel (dados fictícios)."

    @transaction.atomic
    def handle(self, *args, **options):
        if Edital.objects.filter(number="DEMO-CRUD", year=2027).exists():
            self.stdout.write("Demonstração já existente; nenhuma decisão foi sobrescrita.")
            return
        users = {}
        for key, role in {
            "admin": "ADMINISTRADOR",
            "coordenador": "COORDENADOR",
            "distribuidor": "DISTRIBUIDOR",
            "analista": "ANALISTA",
            "revisor": "REVISOR",
            "consulta": "CONSULTA",
        }.items():
            user, created = User.objects.get_or_create(
                username=f"demo.{key}",
                defaults={"role": role, "email": f"{key}@demo.example", "first_name": key.title()},
            )
            if created:
                user.set_password(os.getenv("DEMO_PASSWORD", "Demo.Editais#2027"))
                user.save()
            users[key] = user
        admin = users["admin"]
        now = timezone.now()
        edital = Edital(
            name="Acolhimento comunitário — demonstração",
            number="DEMO-CRUD",
            year=2027,
            opens_at=now - timedelta(days=1),
            closes_at=now + timedelta(days=60),
            rules_version="1.0",
            minimum_equity_percentage=Decimal("12.00"),
            tie_breaker_policy="UNRESOLVED",
        )
        EditalConfigurationService.save(edital, admin)
        municipality, _ = Municipality.objects.get_or_create(
            ibge_code="3106200", defaults={"name": "Belo Horizonte", "state": "MG"}
        )
        other, _ = Municipality.objects.get_or_create(
            ibge_code="3550308", defaults={"name": "São Paulo", "state": "SP"}
        )
        program, _ = Program.objects.get_or_create(
            code="TERRITORIOS-DEMO", defaults={"name": "Territórios prioritários — demonstração"}
        )
        EditalConfigurationService.save(
            ProgramMunicipality(
                edital=edital, program=program, program_name=program.code, municipality=municipality
            ),
            admin,
        )
        for order, code, name, types, group_program in [
            (1, "NUTRIZES", "Mães nutrizes", ["NURSING_MOTHER"], None),
            (2, "FEMININO", "Acolhimento feminino", ["FEMALE"], None),
            (3, "PRIORITARIO", "Masculino em territórios prioritários", ["MALE"], program),
            (4, "GERAL", "Acolhimento masculino", ["MALE"], None),
        ]:
            EditalConfigurationService.save(
                TargetGroup(
                    edital=edital,
                    code=code,
                    name=name,
                    order=order,
                    vacancy_types=types,
                    program=group_program,
                ),
                admin,
            )
        EditalConfigurationService.save(ClassificationPolicy(edital=edital), admin)
        for vacancy_type, value in [
            ("FEMALE", "1000.00"),
            ("MALE", "1100.00"),
            ("NURSING_MOTHER", "1500.00"),
        ]:
            EditalConfigurationService.save(
                FundingRule(
                    edital=edital,
                    vacancy_type=vacancy_type,
                    monthly_value=Decimal(value),
                    duration_months=6,
                ),
                admin,
            )
        direct = EditalConfigurationService.save(
            Requirement(edital=edital, code="INSCRICAO", name="Termo de inscrição", order=1), admin
        )
        req = EditalConfigurationService.save(
            Requirement(
                edital=edital, code="REGULARIDADE", name="Regularidade documental", order=2
            ),
            admin,
        )
        for order, code, name, config in [
            (1, "IDENTIDADE", "Identificação documental", {"collect_document_cnpj": True}),
            (2, "BALANCO", "Capacidade financeira", {"collect_numeric_value": True}),
        ]:
            EditalConfigurationService.save(
                RequirementCheck(requirement=req, code=code, name=name, order=order, **config),
                admin,
            )
        EditalConfigurationService.publish(edital, admin)
        edital.refresh_from_db()
        for index, cnpj in enumerate(["00000000000191", "11222333000181", "00000000E08G12"], 1):
            institution, _ = Institution.objects.get_or_create(
                cnpj=cnpj,
                defaults={
                    "name": f"Instituição demonstrativa {index}",
                    "municipality": municipality,
                },
            )
            sub = Submission.objects.create(
                edital=edital,
                institution=institution,
                processo_sei=f"DEMO-2027-{index:03}",
                received_at=now + timedelta(minutes=index),
                municipality=municipality if index != 3 else other,
                vagas_masculinas=5,
                vagas_solicitadas=5,
                capacidade_total=10,
            )
            sub.valor_global, sub.patrimonio_minimo = FundingService.calculate_submission_values(
                sub
            )
            sub.save(update_fields=["valor_global", "patrimonio_minimo"])
            ClassificationService.classify_and_update(sub, admin)
            WorkflowService.assign_analyst(sub, users["analista"], users["distribuidor"])
            if index == 3:
                continue
            evaluation = EvaluationService.start_evaluation(sub, users["analista"])
            payload = [
                {
                    "check_result_id": cr.pk,
                    "status": "NAO_ATENDE"
                    if index == 2 and cr.requirement_id == direct.pk
                    else "ATENDE",
                }
                for cr in evaluation.check_results.all()
            ]
            EvaluationService.save_draft(evaluation, payload, users["analista"])
            EvaluationService.conclude_evaluation(evaluation, users["analista"])
            if index == 2:
                review = Review.objects.get(evaluation=evaluation)
                ReviewService.claim_review(review, users["revisor"])
                for cr in EvaluationService.blocking_check_results(evaluation):
                    ReviewService.record_item_decision(
                        review,
                        cr.pk,
                        False,
                        "ATENDE",
                        "Documento comprovado após conferência.",
                        users["revisor"],
                    )
                ReviewService.conclude_review(
                    review,
                    "PRE_HABILITADO",
                    "Impedimentos resolvidos na revisão.",
                    users["revisor"],
                )
        RankingService.generate_snapshot(
            edital, users["coordenador"], description="Demonstração de execução sem Excel"
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Demonstração criada: /admin-editais/ e /processos/. Contas demo.admin, demo.analista, demo.revisor, demo.distribuidor, demo.coordenador, demo.consulta."
            )
        )
