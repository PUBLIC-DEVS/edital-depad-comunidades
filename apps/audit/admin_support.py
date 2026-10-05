"""Operational mutations must use domain services, including for administrators."""


class ReadOnlyOperationalAdmin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_view_permission(self, request, obj=None):
        return (
            request.user.is_superuser
            or request.user.role in {"ADMINISTRADOR", "COORDENADOR", "CONSULTA"}
        ) and super().has_view_permission(request, obj)
