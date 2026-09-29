"""Configuration and publication of a new edital, independent of migration sources."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy
from apps.audit.models import AuditEvent

from .models import (
    ClassificationPolicy,
    Edital,
    EditalConfigurationSnapshot,
    FundingRule,
    Program,
    Requirement,
    RequirementValidationRule,
)


def require_configuration_actor(actor):
    if not RolePermissionPolicy.can_manage_editais_and_rules(actor):
        raise PermissionDenied("Somente o administrador configura e publica editais.")


def configuration_data(edital):
    def fields(obj):
        return {
            f.name: str(getattr(obj, f.attname))
            if f.get_internal_type() in {"DecimalField", "DateField", "DateTimeField"}
            and getattr(obj, f.attname) is not None
            else getattr(obj, f.attname)
            for f in obj._meta.concrete_fields
            if f.name not in {"created_at", "updated_at"}
        }

    return {
        "edital": fields(edital),
        "classification_policy": fields(edital.classification_policy),
        "groups": [fields(g) for g in edital.target_groups.all()],
        "requirements": [
            {
                **fields(r),
                "checks": [
                    {
                        **fields(c),
                        "validations": [fields(rule) for rule in c.validation_rules.all()],
                    }
                    for c in r.checks.all()
                ],
            }
            for r in edital.requirements.all()
        ],
        "funding": [fields(f) for f in edital.funding_rules.all().order_by("vacancy_type")],
        "program_municipalities": [
            {
                **fields(p),
                "program_code": p.program.code if p.program else p.program_name,
                "municipality_name": p.municipality.name,
                "municipality_state": p.municipality.state,
                "ibge_code": p.municipality.ibge_code,
            }
            for p in edital.program_municipalities.select_related(
                "program", "municipality"
            ).order_by("pk")
        ],
    }


class EditalConfigurationService:
    @staticmethod
    @transaction.atomic
    def save_program(instance, actor):
        require_configuration_actor(actor)
        created = instance.pk is None
        previous = None
        if instance.pk:
            previous = Program.objects.select_for_update().get(pk=instance.pk)
        instance.full_clean()
        instance.save()
        for field in ("code", "name", "description", "active"):
            old = getattr(previous, field) if previous else ""
            new = getattr(instance, field)
            if created or old != new:
                AuditEvent.objects.create(
                    actor=actor,
                    entity_type="Program",
                    entity_id=str(instance.pk),
                    action="CONFIG_CREATE" if created else "CONFIG_UPDATE",
                    field=field,
                    old_value=str(old),
                    new_value=str(new),
                )
        return instance

    @staticmethod
    def validate(edital):
        errors, warnings, checklist = [], [], []

        def section(label, failures, notes=()):
            errors.extend(failures)
            warnings.extend(notes)
            checklist.append({"label": label, "complete": not failures, "warnings": list(notes)})

        basic = []
        if not edital.name or not edital.number or not edital.rules_version:
            basic.append("Preencha nome, número e versão das regras.")
        if not edital.opens_at or not edital.closes_at or edital.opens_at >= edital.closes_at:
            basic.append("A abertura deve ser anterior ao encerramento.")
        section("Dados gerais", basic)
        groups = list(edital.target_groups.filter(active=True))
        group_errors = [] if groups else ["Cadastre ao menos um grupo ativo."]
        for group in groups:
            try:
                group.full_clean()
            except ValidationError as exc:
                group_errors.extend(exc.messages)
        section("Grupos / públicos", group_errors)
        policy = ClassificationPolicy.objects.filter(edital=edital).first()
        policy_errors = [] if policy else ["Configure a política de classificação."]
        if policy and policy.policy_type in {
            "VACANCY_TARGET_POLICY_V1",
            "VACANCY_TARGET_POLICY_V2_MIXED_FIRST",
        }:
            if any(not g.vacancy_types for g in groups):
                policy_errors.append("Informe os tipos de vaga que enquadram cada grupo.")
            if len({g.order for g in groups}) != len(groups):
                policy_errors.append("Defina prioridades distintas para os grupos.")
        if policy and policy.policy_type == "VACANCY_TARGET_POLICY_V2_MIXED_FIRST":
            if not any(g.code == policy.mixed_group_code for g in groups):
                policy_errors.append("Selecione o grupo para entidades mistas.")
        section(
            "Classificação e duplicidades",
            policy_errors,
            ["Empates absolutos bloquearão o ranking até decisão expressa."]
            if edital.tie_breaker_policy == "UNRESOLVED"
            else [],
        )
        requirements = list(edital.requirements.filter(active=True).prefetch_related("checks"))
        req_errors = [] if requirements else ["Cadastre ao menos um requisito ativo."]
        for req in requirements:
            if req.requires_checks and not req.checks.filter(active=True).exists():
                req_errors.append(f"{req.code}: configure ao menos um subcritério ativo.")
            for definition in [req, *req.checks.filter(active=True)]:
                try:
                    definition.full_clean()
                except ValidationError as exc:
                    req_errors.append(f"{definition.code}: {'; '.join(exc.messages)}")
        section("Requisitos e subcritérios", req_errors)
        validation_errors, validation_warnings = [], []
        for rule in RequirementValidationRule.objects.filter(
            requirement_check__requirement__edital=edital, active=True
        ).select_related("requirement_check__requirement"):
            try:
                rule.full_clean()
            except ValidationError as exc:
                validation_errors.extend(
                    f"{rule.requirement_check.code}: {message}" for message in exc.messages
                )
            if (
                rule.rule_type
                in {
                    RequirementValidationRule.RuleType.DATE_NOT_EXPIRED,
                    RequirementValidationRule.RuleType.CNPJ_MINIMUM_AGE,
                }
                and not edital.validation_reference_date
            ):
                validation_errors.append(
                    f"{rule.requirement_check.code}: configure a data oficial de referência."
                )
            if (
                rule.rule_type == RequirementValidationRule.RuleType.CNAE_REQUIRED
                and isinstance(rule.config, dict)
                and rule.config.get("match_mode") == "UNRESOLVED"
            ):
                validation_warnings.append(
                    "O modo de comparação do CNAE aguarda decisão da coordenação."
                )
                if (
                    rule.severity == RequirementValidationRule.Severity.CRITICAL
                    and rule.blocks_completion
                ):
                    validation_errors.append(
                        f"{rule.requirement_check.code}: resolva o modo do CNAE antes de publicar uma regra crítica."
                    )
        section("Validações automáticas", validation_errors, validation_warnings)
        funding_types = set(edital.funding_rules.values_list("vacancy_type", flat=True))
        needed_types = set().union(*(set(g.vacancy_types) for g in groups)) if groups else set()
        if policy and policy.policy_type == "MANUAL_TARGET_POLICY_V1":
            needed_types = set(FundingRule.VacancyType.values)
        funding_errors = (
            [f"Configure o financiamento para {t}." for t in sorted(needed_types - funding_types)]
            if edital.requires_financial_rules
            else []
        )
        for rule in edital.funding_rules.all():
            try:
                rule.full_clean()
            except ValidationError as exc:
                funding_errors.extend(exc.messages)
        section(
            "Financeiro",
            funding_errors,
            []
            if edital.requires_financial_rules
            else ["Este edital não definiu cálculo financeiro."],
        )
        program_errors = []
        for group in groups:
            if group.program_id and (
                not group.program.active
                or not edital.program_municipalities.filter(
                    program=group.program, active=True
                ).exists()
            ):
                program_errors.append(f"Associe municípios ao programa do grupo {group.code}.")
        section("Programas e municípios", program_errors)
        user_errors = []
        if not User.objects.filter(role=User.Role.ANALISTA, is_active=True).exists():
            user_errors.append("Cadastre ao menos um analista ativo.")
        if (
            any(r.mandatory and r.failure_behavior == "SEND_TO_REVIEW" for r in requirements)
            and not User.objects.filter(role=User.Role.REVISOR, is_active=True).exists()
        ):
            user_errors.append("Cadastre ao menos um revisor ativo.")
        section("Usuários e perfis", user_errors)
        return {
            "errors": errors,
            "warnings": warnings,
            "checklist": checklist,
            "can_publish": not errors,
        }

    @staticmethod
    @transaction.atomic
    def save(instance, actor):
        require_configuration_actor(actor)
        if isinstance(instance, Edital):
            if instance.pk:
                locked = Edital.objects.select_for_update().get(pk=instance.pk)
                if not locked.configuration_editable:
                    raise ValidationError("Edite uma cópia versionada do edital publicado.")
            if instance.status not in {Edital.Status.DRAFT, Edital.Status.CONFIGURING}:
                raise ValidationError("Use a operação Publicar para ativar o edital.")
        else:
            locked = Edital.objects.select_for_update().get(pk=instance.configuration_edital.pk)
            if not locked.configuration_editable:
                raise ValidationError("Configuração publicada está protegida.")
        created = instance.pk is None
        instance.full_clean()
        instance.save()
        AuditEvent.objects.create(
            actor=actor,
            entity_type=type(instance).__name__,
            entity_id=str(instance.pk),
            action="CONFIG_CREATE" if created else "CONFIG_UPDATE",
            metadata={
                "edital_id": instance.pk
                if isinstance(instance, Edital)
                else instance.configuration_edital.pk
            },
        )
        return instance

    @staticmethod
    @transaction.atomic
    def publish(edital, actor):
        require_configuration_actor(actor)
        edital = Edital.objects.select_for_update().get(pk=edital.pk)
        if not edital.configuration_editable:
            raise ValidationError("Edital já publicado ou encerrado.")
        validation = EditalConfigurationService.validate(edital)
        if validation["errors"]:
            raise ValidationError(validation["errors"])
        snapshot = EditalConfigurationSnapshot.objects.create(
            edital=edital,
            rules_version=edital.rules_version,
            configuration=configuration_data(edital),
            published_by=actor,
        )
        old = edital.status
        edital.status = Edital.Status.ACTIVE
        edital.published_at = timezone.now()
        edital.published_by = actor
        edital.save()
        AuditEvent.objects.create(
            actor=actor,
            entity_type="Edital",
            entity_id=str(edital.pk),
            action="PUBLISH",
            field="status",
            old_value=old,
            new_value=edital.status,
            metadata={
                "configuration_snapshot_id": snapshot.pk,
                "rules_version": edital.rules_version,
            },
        )
        return snapshot

    @staticmethod
    @transaction.atomic
    def clone(source, actor, **new_data):
        require_configuration_actor(actor)
        source = Edital.objects.select_for_update().get(pk=source.pk)
        defaults = {
            field: getattr(source, field)
            for field in (
                "description",
                "duplicate_policy",
                "duplicate_scope",
                "tie_breaker_policy",
                "minimum_equity_percentage",
                "requires_financial_rules",
            )
        }
        defaults.update(new_data)
        clone = Edital(cloned_from=source, status=Edital.Status.DRAFT, **defaults)
        clone.full_clean()
        clone.save()

        def copy(obj, **relationships):
            values = {
                f.attname: getattr(obj, f.attname)
                for f in obj._meta.concrete_fields
                if not f.primary_key
                and f.name not in {"created_at", "updated_at"}
                and f.name not in relationships
            }
            return type(obj).objects.create(**values, **relationships)

        for obj in source.target_groups.all():
            copy(obj, edital=clone)
        for req in source.requirements.all():
            new_req = copy(req, edital=clone)
            for check in req.checks.all():
                new_check = copy(check, requirement=new_req)
                for rule in check.validation_rules.all():
                    copy(rule, requirement_check=new_check)
        for obj in source.funding_rules.all():
            copy(obj, edital=clone)
        for obj in source.program_municipalities.all():
            copy(obj, edital=clone)
        policy = ClassificationPolicy.objects.filter(edital=source).first()
        if policy:
            copy(policy, edital=clone)
        AuditEvent.objects.create(
            actor=actor,
            entity_type="Edital",
            entity_id=str(clone.pk),
            action="CLONE_CONFIGURATION",
            metadata={"source_edital_id": source.pk, "source_rules_version": source.rules_version},
        )
        return clone

    @staticmethod
    @transaction.atomic
    def set_status(edital, status, actor):
        require_configuration_actor(actor)
        edital = Edital.objects.select_for_update().get(pk=edital.pk)
        allowed = {"ACTIVE": {"CLOSED"}, "CLOSED": {"ARCHIVED"}}
        if status not in allowed.get(edital.status, set()):
            raise ValidationError("Transição de edital inválida.")
        old = edital.status
        edital.status = status
        edital.save(update_fields=["status", "updated_at"])
        AuditEvent.objects.create(
            actor=actor,
            entity_type="Edital",
            entity_id=str(edital.pk),
            action="EDT_STATUS",
            field="status",
            old_value=old,
            new_value=status,
        )
        return edital

    @staticmethod
    @transaction.atomic
    def reorder(instance, direction, actor):
        require_configuration_actor(actor)
        edital = Edital.objects.select_for_update().get(pk=instance.configuration_edital.pk)
        if not edital.configuration_editable:
            raise ValidationError("Configuração publicada está protegida.")
        peers = list(
            type(instance)
            .objects.filter(
                **(
                    {"edital": edital}
                    if isinstance(instance, Requirement)
                    else {"requirement": instance.requirement}
                )
            )
            .order_by("order", "pk")
        )
        index = next(i for i, peer in enumerate(peers) if peer.pk == instance.pk)
        target = index + (-1 if direction == "up" else 1)
        if direction not in {"up", "down"}:
            raise ValidationError("Direção inválida.")
        if 0 <= target < len(peers):
            peers[index], peers[target] = peers[target], peers[index]
            for position, peer in enumerate(peers, 1):
                if peer.order != position:
                    peer.order = position
                    peer.save(update_fields=["order"])
            AuditEvent.objects.create(
                actor=actor,
                entity_type=type(instance).__name__,
                entity_id=str(instance.pk),
                action="REORDER",
                metadata={"direction": direction, "edital_id": edital.pk},
            )
