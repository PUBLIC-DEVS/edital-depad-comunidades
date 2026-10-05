from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name", "upn", "azure_oid")
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Perfil e Integração Institucional",
            {
                "fields": ("role", "azure_oid", "upn"),
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Perfil e Integração Institucional",
            {
                "fields": ("role", "email"),
            },
        ),
    )
