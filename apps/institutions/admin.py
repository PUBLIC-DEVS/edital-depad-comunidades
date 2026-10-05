from django.contrib import admin

from .models import Institution, Municipality


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ("ibge_code", "name", "state")
    search_fields = ("ibge_code", "name", "state")
    list_filter = ("state",)


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("cnpj", "name", "trade_name", "municipality", "created_at")
    search_fields = ("cnpj", "name", "trade_name")
    list_filter = ("municipality__state",)
