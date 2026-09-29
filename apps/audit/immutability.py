from django.core.exceptions import PermissionDenied
from django.db import models


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied("Registro append-only não pode ser alterado.")

    def delete(self):
        raise PermissionDenied("Registro append-only não pode ser excluído.")

    def bulk_update(self, objs, fields, **kwargs):
        raise PermissionDenied("Registro append-only não pode ser alterado em lote.")

    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise PermissionDenied("Registro append-only não aceita substituição por conflito.")
        return super().bulk_create(objs, **kwargs)
