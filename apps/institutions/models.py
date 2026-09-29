from django.core.exceptions import ValidationError
from django.db import models

from .cnpj import cnpj_validator, format_cnpj, normalize_cnpj


class Municipality(models.Model):
    """Representa um município brasileiro com código oficial do IBGE."""

    ibge_code = models.CharField(
        max_length=7,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Código IBGE",
        help_text="Código IBGE oficial de 7 dígitos.",
    )
    name = models.CharField(max_length=150, verbose_name="Nome do Município")
    state = models.CharField(max_length=2, verbose_name="UF", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Município"
        verbose_name_plural = "Municípios"
        ordering = ["state", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "state"],
                condition=models.Q(ibge_code__isnull=True),
                name="unique_unresolved_municipality_name_state",
            ),
        ]

    def __str__(self):
        return f"{self.name}/{self.state} ({self.ibge_code})"


class Institution(models.Model):
    """Representa a entidade proponente / organização da sociedade civil."""

    cnpj = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        validators=[cnpj_validator],
        verbose_name="CNPJ",
        help_text="CNPJ da instituição (normalizado, 14 dígitos numéricos ou padrão alfanumérico).",
    )
    name = models.CharField(max_length=255, verbose_name="Razão Social")
    trade_name = models.CharField(max_length=255, blank=True, verbose_name="Nome Fantasia")
    legal_nature = models.CharField(max_length=100, blank=True, verbose_name="Natureza Jurídica")
    contact_email = models.EmailField(blank=True, verbose_name="E-mail de Contato")
    contact_phone = models.CharField(max_length=50, blank=True, verbose_name="Telefone de Contato")
    address = models.CharField(max_length=255, blank=True, verbose_name="Endereço")
    postal_code = models.CharField(max_length=9, blank=True, verbose_name="CEP")
    municipality = models.ForeignKey(
        Municipality,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="institutions",
        verbose_name="Município Sede",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Instituição"
        verbose_name_plural = "Instituições"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} - {self.formatted_cnpj}"

    def save(self, *args, **kwargs):
        normalized = normalize_cnpj(self.cnpj)
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.cnpj != normalized and previous.submissions.exists():
                raise ValidationError("CNPJ de instituição com processos registrados é imutável.")
        self.cnpj = normalized
        super().save(*args, **kwargs)

    @property
    def formatted_cnpj(self) -> str:
        return format_cnpj(self.cnpj)
