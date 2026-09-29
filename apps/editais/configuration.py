"""Ordinary ORM protection for configuration once an edital is published."""

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models, transaction

MUTABLE_STATUSES = {"DRAFT", "CONFIGURING"}


class ConfigurationQuerySet(models.QuerySet):
    def _guard(self):
        path = self.model.configuration_edital_path
        ids = self.values_list(f"{path}pk", flat=True).distinct()
        edital_model = apps.get_model("editais", "Edital")
        editais = list(edital_model.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        if any(edital.status not in MUTABLE_STATUSES for edital in editais):
            raise ValidationError(
                "Configuração publicada é protegida. Duplique para uma nova versão."
            )

    @transaction.atomic
    def update(self, **kwargs):
        self._guard()
        for field in ("edital", "requirement"):
            value = kwargs.get(field, kwargs.get(f"{field}_id"))
            if value is not None and self.model._meta.get_field(field).is_relation:
                target = (
                    value
                    if isinstance(value, models.Model)
                    else self.model._meta.get_field(field).remote_field.model.objects.get(pk=value)
                )
                edital = target if field == "edital" else target.edital
                if (
                    not type(edital)
                    .objects.filter(pk=edital.pk, status__in=MUTABLE_STATUSES)
                    .exists()
                ):
                    raise ValidationError("Não associe regras a um edital publicado.")
        return super().update(**kwargs)

    @transaction.atomic
    def delete(self):
        self._guard()
        return super().delete()

    @transaction.atomic
    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("Use alterações auditadas, sem upsert de configuração.")
        objs = list(objs)
        for obj in objs:
            obj.assert_mutable()
        return super().bulk_create(objs, **kwargs)

    @transaction.atomic
    def bulk_update(self, objs, fields, **kwargs):
        objs = list(objs)
        self.filter(pk__in=[obj.pk for obj in objs])._guard()
        for obj in objs:
            obj.assert_mutable()
        return super().bulk_update(objs, fields, **kwargs)


class ConfigurationModel(models.Model):
    objects = ConfigurationQuerySet.as_manager()
    configuration_edital_path = "edital__"

    class Meta:
        abstract = True

    @property
    def configuration_edital(self):
        return self.edital

    def assert_mutable(self):
        edital = self.configuration_edital
        status = (
            type(edital)
            .objects.select_for_update()
            .values_list("status", flat=True)
            .get(pk=edital.pk)
        )
        if status not in MUTABLE_STATUSES:
            raise ValidationError(
                "Configuração publicada é protegida. Duplique para uma nova versão."
            )

    @transaction.atomic
    def save(self, *args, **kwargs):
        # An idempotent migration read must not be treated as a rule amendment.
        existing = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        fields = [
            f.attname
            for f in self._meta.concrete_fields
            if not f.auto_created and f.name not in {"created_at", "updated_at"}
        ]
        if existing is None or any(getattr(existing, f) != getattr(self, f) for f in fields):
            if existing is not None:
                existing.assert_mutable()
            self.assert_mutable()
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        self.assert_mutable()
        return super().delete(*args, **kwargs)


class EditalQuerySet(models.QuerySet):
    @transaction.atomic
    def update(self, **kwargs):
        editais = list(self.select_for_update())
        if "status" in kwargs or any(edital.status not in MUTABLE_STATUSES for edital in editais):
            raise ValidationError("Use as operações auditadas de configuração/publicação.")
        return super().update(**kwargs)

    @transaction.atomic
    def delete(self):
        editais = list(self.select_for_update())
        if any(edital.status not in MUTABLE_STATUSES for edital in editais):
            raise ValidationError("Edital publicado deve ser arquivado, nunca removido.")
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Crie editais pelo serviço auditado; publicação exige snapshot.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Use o serviço de configuração para alterações de editais.")
