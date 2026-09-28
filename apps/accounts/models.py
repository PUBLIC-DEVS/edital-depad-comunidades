from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Gerenciador customizado para o modelo de usuário."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError("O nome de usuário é obrigatório.")
        if email:
            email = self.normalize_email(email)
        extra_fields.setdefault("role", User.Role.CONSULTA)
        user = self.model(username=username, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMINISTRADOR)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário deve ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário deve ter is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """Modelo de usuário customizado compatível com autenticação local e Microsoft Entra ID."""

    class Role(models.TextChoices):
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
        COORDENADOR = "COORDENADOR", "Coordenador"
        DISTRIBUIDOR = "DISTRIBUIDOR", "Distribuidor"
        ANALISTA = "ANALISTA", "Analista"
        REVISOR = "REVISOR", "Revisor"
        CONSULTA = "CONSULTA", "Consulta"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CONSULTA,
        verbose_name="Papel no Sistema",
        help_text="Perfil funcional que define as permissões operacionais do usuário.",
    )
    email = models.EmailField(
        unique=True,
        verbose_name="E-mail Institucional",
    )
    azure_oid = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        unique=True,
        verbose_name="ID Objeto Azure/Entra",
        help_text="Identificador único global do usuário no Microsoft Entra ID.",
    )
    upn = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="User Principal Name (UPN)",
        help_text="Identificador institucional corporativo Microsoft (ex: nome@mds.gov.br).",
    )

    objects = UserManager()

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        ordering = ["username"]

    def __str__(self):
        full_name = self.get_full_name()
        display = full_name if full_name else self.username
        return f"{display} ({self.get_role_display()})"

    @property
    def is_analyst(self) -> bool:
        return self.role == self.Role.ANALISTA or self.is_superuser

    @property
    def is_reviewer(self) -> bool:
        return self.role == self.Role.REVISOR or self.is_superuser

    @property
    def is_distributor(self) -> bool:
        allowed = (self.Role.DISTRIBUIDOR, self.Role.COORDENADOR, self.Role.ADMINISTRADOR)
        return self.role in allowed or self.is_superuser

    @property
    def is_coordinator(self) -> bool:
        return self.role in (self.Role.COORDENADOR, self.Role.ADMINISTRADOR) or self.is_superuser

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMINISTRADOR or self.is_superuser
