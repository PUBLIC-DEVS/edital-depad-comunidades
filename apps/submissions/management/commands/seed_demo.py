"""Comando para popular o banco de dados com cenário completo e realista de demonstração."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import (
    Edital,
    FundingRule,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
)
from apps.evaluations.models import CheckResult, Evaluation
from apps.institutions.models import Institution, Municipality
from apps.ranking.models import RankingSnapshot
from apps.ranking.services.classification import ClassificationService
from apps.reviews.models import Diligence, Review, ReviewItemDecision
from apps.submissions.models import Assignment, Submission


class Command(BaseCommand):
    help = "Popula o banco de dados com um cenário demonstrativo completo, auditável e realista."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.NOTICE("Iniciando população de dados de demonstração (seed_demo)...")
        )

        with transaction.atomic():
            # 1. Usuários de Demonstração
            admin_user, _ = User.objects.get_or_create(
                username="admin",
                defaults={
                    "email": "admin@mds.gov.br",
                    "first_name": "Administrador",
                    "last_name": "Geral",
                    "role": User.Role.ADMINISTRADOR,
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            admin_user.set_password("admin12345")
            admin_user.save()

            coord_user, _ = User.objects.get_or_create(
                username="coordenador",
                defaults={
                    "email": "coordenador@mds.gov.br",
                    "first_name": "Claudio",
                    "last_name": "Menezes",
                    "role": User.Role.COORDENADOR,
                },
            )
            coord_user.set_password("coord12345")
            coord_user.save()

            dist_user, _ = User.objects.get_or_create(
                username="distribuidor",
                defaults={
                    "email": "distribuidor@mds.gov.br",
                    "first_name": "Patrícia",
                    "last_name": "Lima",
                    "role": User.Role.DISTRIBUIDOR,
                },
            )
            dist_user.set_password("dist12345")
            dist_user.save()

            analyst_ana, _ = User.objects.get_or_create(
                username="ana.paula",
                defaults={
                    "email": "ana.paula@mds.gov.br",
                    "first_name": "Ana Paula",
                    "last_name": "Ferreira",
                    "role": User.Role.ANALISTA,
                },
            )
            analyst_ana.set_password("analista12345")
            analyst_ana.save()

            analyst_daniel, _ = User.objects.get_or_create(
                username="daniel.silva",
                defaults={
                    "email": "daniel.silva@mds.gov.br",
                    "first_name": "Daniel",
                    "last_name": "Silva",
                    "role": User.Role.ANALISTA,
                },
            )
            analyst_daniel.set_password("analista12345")
            analyst_daniel.save()

            analyst_carlos, _ = User.objects.get_or_create(
                username="carlos.eduardo",
                defaults={
                    "email": "carlos.eduardo@mds.gov.br",
                    "first_name": "Carlos Eduardo",
                    "last_name": "Rocha",
                    "role": User.Role.ANALISTA,
                },
            )
            analyst_carlos.set_password("analista12345")
            analyst_carlos.save()

            rev_user, _ = User.objects.get_or_create(
                username="revisor",
                defaults={
                    "email": "revisor@mds.gov.br",
                    "first_name": "Mariana",
                    "last_name": "Barbosa",
                    "role": User.Role.REVISOR,
                },
            )
            rev_user.set_password("revisor12345")
            rev_user.save()

            consulta_user, _ = User.objects.get_or_create(
                username="consulta",
                defaults={
                    "email": "consulta@mds.gov.br",
                    "first_name": "Auditoria",
                    "last_name": "Externa",
                    "role": User.Role.CONSULTA,
                },
            )
            consulta_user.set_password("consulta12345")
            consulta_user.save()

            # 2. Edital e Parâmetros
            edital, _ = Edital.objects.get_or_create(
                number="01",
                year=2026,
                defaults={
                    "name": "Edital de Apoio a Comunidades Terapêuticas e Acolhimento",
                    "status": Edital.Status.PUBLISHED,
                    "opens_at": timezone.now() - timezone.timedelta(days=45),
                    "closes_at": timezone.now() + timezone.timedelta(days=15),
                    "rules_version": "1.0",
                },
            )

            # Regras por tipo de vaga; nunca derivadas dos grupos G1/G2/G3.
            for vacancy_type, amount in [
                ("FEMALE", "1172.23"),
                ("MALE", "1172.23"),
                ("NURSING_MOTHER", "1527.37"),
            ]:
                FundingRule.objects.get_or_create(
                    edital=edital,
                    vacancy_type=vacancy_type,
                    defaults={"monthly_value": Decimal(amount), "duration_months": 12},
                )

            # Requisitos Documentais e Subcritérios
            req_data = [
                (
                    "4.2-I",
                    "Requerimento de Inscrição",
                    "Formulário padronizado assinado pelo representante legal.",
                    True,
                    1,
                ),
                (
                    "4.2-II",
                    "CNPJ Regular",
                    "Comprovante de inscrição e de situação cadastral na RFB com CNAE compatível.",
                    True,
                    2,
                ),
                (
                    "4.2-III",
                    "Certidão de Regularidade Fiscal Federal",
                    "Certidão Conjunta Negativa da Receita Federal e PGFN.",
                    True,
                    3,
                ),
                (
                    "4.2-IV",
                    "Certificado de Regularidade do FGTS",
                    "CRF expedido pela Caixa Econômica Federal em vigor.",
                    True,
                    4,
                ),
                (
                    "4.2-V",
                    "Estatuto Social Registrado",
                    "Estatuto com finalidade compatível, ausência de remuneração e dissolução sem fins lucrativos.",
                    True,
                    5,
                ),
                (
                    "4.2-VI",
                    "Ata de Eleição da Diretoria",
                    "Ata devidamente averbada em cartório com mandato vigente.",
                    True,
                    6,
                ),
                (
                    "4.2-VII",
                    "Alvará Sanitário / Licença de Funcionamento",
                    "Alvará expedido pela Vigilância Sanitária municipal ou estadual.",
                    True,
                    7,
                ),
                (
                    "4.2-VIII",
                    "Capacidade Instalada e Infraestrutura",
                    "Laudo técnico de vistoria demonstrando infraestrutura física adequada.",
                    True,
                    8,
                ),
                (
                    "4.2-XVI",
                    "Declaração de Idoneidade e Não Parentesco",
                    "Declaração de não impedimento e ausência de nepotismo assinada.",
                    True,
                    9,
                ),
            ]

            checks_map = {}
            for code, name, desc, mandatory, order in req_data:
                req, _ = Requirement.objects.get_or_create(
                    edital=edital,
                    code=code,
                    defaults={
                        "name": name,
                        "description": desc,
                        "mandatory": mandatory,
                        "order": order,
                    },
                )
                check, _ = RequirementCheck.objects.get_or_create(
                    requirement=req,
                    name=f"Conferência de {name}",
                    defaults={"order": 1},
                )
                checks_map[code] = check

            # 3. Municípios e PRONASCI
            muni_sp, _ = Municipality.objects.get_or_create(
                ibge_code="3550308", defaults={"name": "São Paulo", "state": "SP"}
            )
            muni_rj, _ = Municipality.objects.get_or_create(
                ibge_code="3304557", defaults={"name": "Rio de Janeiro", "state": "RJ"}
            )
            muni_bh, _ = Municipality.objects.get_or_create(
                ibge_code="3106200", defaults={"name": "Belo Horizonte", "state": "MG"}
            )
            muni_camp, _ = Municipality.objects.get_or_create(
                ibge_code="3509502", defaults={"name": "Campinas", "state": "SP"}
            )
            muni_join, _ = Municipality.objects.get_or_create(
                ibge_code="4209102", defaults={"name": "Joinville", "state": "SC"}
            )

            for m in [muni_sp, muni_rj, muni_bh]:
                ProgramMunicipality.objects.get_or_create(
                    edital=edital,
                    municipality=m,
                    program_name="PRONASCI",
                    defaults={"active": True},
                )

            # 4. Instituições
            inst_data = [
                ("01234567000189", "Instituto Renascer de Amparo à Mulher", muni_sp),
                ("12345678000190", "Comunidade Terapêutica Esperança Viva", muni_rj),
                ("23456789000101", "Associação Beneficente Caminho da Luz", muni_bh),
                ("34567890000112", "Centro de Reabilitação Vida Plena", muni_camp),
                ("45678901000123", "Casa de Passagem e Acolhimento Sul", muni_join),
                ("56789012000134", "Fraternidade Irmão Sol", muni_sp),
                ("67890123000145", "Obra Social Bom Pastor", muni_camp),
                ("78901234000156", "Associação Resgate e Cidadania", muni_rj),
            ]

            institutions = {}
            for cnpj, name, muni in inst_data:
                inst, _ = Institution.objects.get_or_create(
                    cnpj=cnpj,
                    defaults={"name": name, "municipality": muni},
                )
                institutions[cnpj] = inst

            # 5. Submissões em Diversos Estados de Workflow
            now = timezone.now()

            # Processo 1 - G1, CONCLUÍDO / APTO, com Review Confirmada
            sub1, _ = Submission.objects.get_or_create(
                edital=edital,
                processo_sei="71000.001001/2026-11",
                defaults={
                    "institution": institutions["01234567000189"],
                    "municipality": muni_sp,
                    "received_at": now - timezone.timedelta(days=20, hours=2),
                    "vagas_femininas": 15,
                    "vagas_masculinas": 0,
                    "vagas_maes_nutrizes": 5,
                    "vagas_solicitadas": 20,
                    "capacidade_total": 35,
                    "valor_global": Decimal("360000.00"),
                    "workflow_status": Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
                },
            )
            Assignment.objects.get_or_create(
                submission=sub1,
                analyst=analyst_ana,
                defaults={"assigned_by": dist_user, "status": Assignment.Status.ACTIVE},
            )
            eval1, _ = Evaluation.objects.get_or_create(
                submission=sub1,
                defaults={
                    "analyst": analyst_ana,
                    "status": Evaluation.Status.COMPLETED,
                    "result": Evaluation.Result.APTA,
                },
            )
            for chk in checks_map.values():
                CheckResult.objects.get_or_create(
                    evaluation=eval1,
                    requirement_check=chk,
                    defaults={"status": CheckResult.Status.ATENDE, "notes": "Em conformidade"},
                )
            rev1, _ = Review.objects.get_or_create(
                evaluation=eval1,
                defaults={
                    "submission": sub1,
                    "reviewer": rev_user,
                    "status": Review.Status.COMPLETED,
                    "preliminary_result": Review.PreliminaryResult.PRE_HABILITADO,
                    "decision_notes": "Concordância integral com a análise documental.",
                },
            )

            # Processo 2 - G2 (PRONASCI), INABILITADO / INAPTO por CND Vencida
            sub2, _ = Submission.objects.get_or_create(
                edital=edital,
                processo_sei="71000.001002/2026-22",
                defaults={
                    "institution": institutions["12345678000190"],
                    "municipality": muni_rj,
                    "received_at": now - timezone.timedelta(days=20, hours=1),
                    "vagas_femininas": 0,
                    "vagas_masculinas": 25,
                    "vagas_maes_nutrizes": 0,
                    "vagas_solicitadas": 25,
                    "capacidade_total": 40,
                    "valor_global": Decimal("390000.00"),
                    "workflow_status": Submission.WorkflowStatus.INELIGIBLE,
                },
            )
            Assignment.objects.get_or_create(
                submission=sub2,
                analyst=analyst_daniel,
                defaults={"assigned_by": dist_user, "status": Assignment.Status.ACTIVE},
            )
            eval2, _ = Evaluation.objects.get_or_create(
                submission=sub2,
                defaults={
                    "analyst": analyst_daniel,
                    "status": Evaluation.Status.COMPLETED,
                    "result": Evaluation.Result.INAPTA,
                },
            )
            for code, chk in checks_map.items():
                if code == "4.2-III":
                    CheckResult.objects.get_or_create(
                        evaluation=eval2,
                        requirement_check=chk,
                        defaults={
                            "status": CheckResult.Status.NAO_ATENDE,
                            "notes": "Certidão vencida em 10/01/2026",
                        },
                    )
                else:
                    CheckResult.objects.get_or_create(
                        evaluation=eval2,
                        requirement_check=chk,
                        defaults={"status": CheckResult.Status.ATENDE},
                    )

            # Processo 3 - G3 (Ampla), EM DILIGÊNCIA (Alvará Sanitário vencido)
            sub3, _ = Submission.objects.get_or_create(
                edital=edital,
                processo_sei="71000.001003/2026-33",
                defaults={
                    "institution": institutions["34567890000112"],
                    "municipality": muni_camp,
                    "received_at": now - timezone.timedelta(days=19),
                    "vagas_femininas": 0,
                    "vagas_masculinas": 20,
                    "vagas_maes_nutrizes": 0,
                    "vagas_solicitadas": 20,
                    "capacidade_total": 30,
                    "valor_global": Decimal("264000.00"),
                    "workflow_status": Submission.WorkflowStatus.PENDING_DILIGENCE,
                },
            )
            Assignment.objects.get_or_create(
                submission=sub3,
                analyst=analyst_ana,
                defaults={"assigned_by": dist_user, "status": Assignment.Status.ACTIVE},
            )
            Diligence.objects.get_or_create(
                submission=sub3,
                reason="Solicitação do protocolo de renovação do Alvará Sanitário 2026.",
                defaults={
                    "requested_by": coord_user,
                    "requested_at": now - timezone.timedelta(days=2),
                    "deadline": now.date() + timezone.timedelta(days=8),
                    "status": Diligence.Status.OPEN,
                },
            )

            # Processo 4 - G3, PENDENTE DE REVISÃO (com divergência registrada pelo Revisor)
            sub4, _ = Submission.objects.get_or_create(
                edital=edital,
                processo_sei="71000.001004/2026-44",
                defaults={
                    "institution": institutions["45678901000123"],
                    "municipality": muni_join,
                    "received_at": now - timezone.timedelta(days=18),
                    "vagas_femininas": 0,
                    "vagas_masculinas": 15,
                    "vagas_maes_nutrizes": 0,
                    "vagas_solicitadas": 15,
                    "capacidade_total": 20,
                    "valor_global": Decimal("198000.00"),
                    "workflow_status": Submission.WorkflowStatus.PENDING_REVIEW,
                },
            )
            Assignment.objects.get_or_create(
                submission=sub4,
                analyst=analyst_carlos,
                defaults={"assigned_by": dist_user, "status": Assignment.Status.ACTIVE},
            )
            eval4, _ = Evaluation.objects.get_or_create(
                submission=sub4,
                defaults={
                    "analyst": analyst_carlos,
                    "status": Evaluation.Status.COMPLETED,
                    "result": Evaluation.Result.APTA,
                },
            )
            cr_estatuto, _ = CheckResult.objects.get_or_create(
                evaluation=eval4,
                requirement_check=checks_map["4.2-V"],
                defaults={"status": CheckResult.Status.ATENDE},
            )
            rev4, _ = Review.objects.get_or_create(
                evaluation=eval4,
                defaults={
                    "submission": sub4,
                    "reviewer": rev_user,
                    "status": Review.Status.COMPLETED,
                    "preliminary_result": Review.PreliminaryResult.PRE_INABILITADO,
                    "decision_notes": "Divergência técnica: o Estatuto não prevê expressamente a cláusula de não remuneração de diretores.",
                },
            )
            ReviewItemDecision.objects.get_or_create(
                review=rev4,
                check_result=cr_estatuto,
                defaults={
                    "agrees_with_analyst": False,
                    "reviewer_status": CheckResult.Status.NAO_ATENDE,
                    "justification": "Artigo 45 ausente no estatuto consolidado juntado aos autos.",
                },
            )

            # Processo 5 - EM ANÁLISE (com Analista Carlos)
            sub5, _ = Submission.objects.get_or_create(
                edital=edital,
                processo_sei="71000.001005/2026-55",
                defaults={
                    "institution": institutions["56789012000134"],
                    "municipality": muni_sp,
                    "received_at": now - timezone.timedelta(days=17),
                    "vagas_femininas": 10,
                    "vagas_masculinas": 0,
                    "vagas_maes_nutrizes": 0,
                    "vagas_solicitadas": 10,
                    "capacidade_total": 15,
                    "valor_global": Decimal("180000.00"),
                    "workflow_status": Submission.WorkflowStatus.UNDER_ANALYSIS,
                },
            )
            Assignment.objects.get_or_create(
                submission=sub5,
                analyst=analyst_carlos,
                defaults={"assigned_by": dist_user, "status": Assignment.Status.ACTIVE},
            )

            # Processo 6 - DISTRIBUÍDO (Aguardando início pelo analista Daniel)
            sub6, _ = Submission.objects.get_or_create(
                edital=edital,
                processo_sei="71000.001006/2026-66",
                defaults={
                    "institution": institutions["67890123000145"],
                    "municipality": muni_camp,
                    "received_at": now - timezone.timedelta(days=16),
                    "vagas_femininas": 0,
                    "vagas_masculinas": 12,
                    "vagas_maes_nutrizes": 0,
                    "vagas_solicitadas": 12,
                    "capacidade_total": 20,
                    "valor_global": Decimal("158400.00"),
                    "workflow_status": Submission.WorkflowStatus.ASSIGNED,
                },
            )
            Assignment.objects.get_or_create(
                submission=sub6,
                analyst=analyst_daniel,
                defaults={"assigned_by": dist_user, "status": Assignment.Status.ACTIVE},
            )

            # Processo 7 - RECEBIDO (Ainda não distribuído)
            sub7, _ = Submission.objects.get_or_create(
                edital=edital,
                processo_sei="71000.001007/2026-77",
                defaults={
                    "institution": institutions["78901234000156"],
                    "municipality": muni_rj,
                    "received_at": now - timezone.timedelta(days=15),
                    "vagas_femininas": 0,
                    "vagas_masculinas": 30,
                    "vagas_maes_nutrizes": 0,
                    "vagas_solicitadas": 30,
                    "capacidade_total": 50,
                    "valor_global": Decimal("468000.00"),
                    "workflow_status": Submission.WorkflowStatus.RECEIVED,
                },
            )

            # Classifica todos
            for s in [sub1, sub2, sub3, sub4, sub5, sub6, sub7]:
                ClassificationService.classify_and_update(s)

            # Official snapshot goes through the same service as production.
            from apps.ranking.services import RankingService

            if not RankingSnapshot.objects.filter(edital=edital).exists():
                RankingService.generate_snapshot(edital, coord_user, description="Demonstração")

            # 7. Eventos de Auditoria
            AuditEvent.objects.create(
                actor=coord_user,
                action="SEED_DEMO",
                entity_type="System",
                entity_id=str(edital.id),
                metadata={"status": "Ambiente de demonstração populado com sucesso."},
            )

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 65))
        self.stdout.write(self.style.SUCCESS(" AMBIENTE DE DEMONSTRAÇÃO POPULADO COM SUCESSO!"))
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write("\nCredenciais de Acesso (Login / Senha):")
        self.stdout.write(" - Administrador:  admin         / admin12345")
        self.stdout.write(" - Coordenador:    coordenador   / coord12345")
        self.stdout.write(" - Distribuidor:   distribuidor  / dist12345")
        self.stdout.write(" - Analista 1:     ana.paula     / analista12345")
        self.stdout.write(" - Analista 2:     daniel.silva  / analista12345")
        self.stdout.write(" - Analista 3:     carlos.eduardo / analista12345")
        self.stdout.write(" - Revisor:        revisor       / revisor12345")
        self.stdout.write(" - Consulta:       consulta      / consulta12345")
        self.stdout.write("\nCenários Criados:")
        self.stdout.write(
            " - Processos: Recebidos, Distribuídos, Sob Análise, Em Revisão, Diligência, Aptos e Inaptos."
        )
        self.stdout.write(" - Ranking Snapshot preliminar v1 gerado e publicado.")
        self.stdout.write("=" * 65 + "\n")
