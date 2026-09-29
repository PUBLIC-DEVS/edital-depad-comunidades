from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy, ScopedQuerySetSelector, require_role
from apps.audit.models import AuditEvent
from apps.editais.models import Program
from apps.institutions.models import Institution, Municipality

from .forms import InstitutionForm, MunicipalityForm, ProgramForm, UserForm

CATALOGS = {
    "instituicoes": (Institution, InstitutionForm, "Instituições"),
    "municipios": (Municipality, MunicipalityForm, "Municípios"),
    "programas": (Program, ProgramForm, "Programas"),
    "usuarios": (User, UserForm, "Usuários e perfis"),
}


def catalog_access(user, catalog, write=False):
    if catalog == "instituicoes":
        if write and not RolePermissionPolicy.can_distribute_submissions(user):
            raise PermissionDenied("Cadastro institucional restrito à equipe de distribuição.")
        return
    if write:
        allowed = RolePermissionPolicy.can_manage_editais_and_rules(user)
    else:
        allowed = user.is_superuser or user.role in {User.Role.ADMINISTRADOR, User.Role.COORDENADOR}
    if not allowed:
        raise PermissionDenied("Configuração administrativa restrita.")


def catalog_definition(catalog):
    from django.http import Http404

    if catalog not in CATALOGS:
        raise Http404
    return CATALOGS[catalog]


def scoped_institutions(user):
    if RolePermissionPolicy.can_view_all_submissions(user):
        return Institution.objects.all()
    return Institution.objects.filter(
        submissions__in=ScopedQuerySetSelector.for_submissions(user)
    ).distinct()


@login_required
@require_role(User.Role.ADMINISTRADOR, User.Role.COORDENADOR)
def index(request):
    return render(request, "administration/index.html")


@login_required
def catalog_list(request, catalog):
    model, _, title = catalog_definition(catalog)
    catalog_access(request.user, catalog)
    objects = (
        scoped_institutions(request.user) if catalog == "instituicoes" else model.objects.all()
    )
    search = request.GET.get("q", "").strip()
    if search:
        name_field = "username" if catalog == "usuarios" else "name"
        objects = objects.filter(**{f"{name_field}__icontains": search})
    can_write = (
        RolePermissionPolicy.can_distribute_submissions(request.user)
        if catalog == "instituicoes"
        else RolePermissionPolicy.can_manage_editais_and_rules(request.user)
    )
    from django.core.paginator import Paginator

    page = Paginator(objects.order_by("pk"), 30).get_page(request.GET.get("page"))
    return render(
        request,
        "administration/catalog.html",
        {
            "catalog": catalog,
            "title": title,
            "page": page,
            "can_write": can_write,
            "search": search,
        },
    )


@login_required
@transaction.atomic
def catalog_form(request, catalog, object_id=None):
    model, form_type, title = catalog_definition(catalog)
    catalog_access(request.user, catalog, write=True)
    instance = (
        get_object_or_404(model.objects.select_for_update(), pk=object_id) if object_id else model()
    )
    if isinstance(instance, User) and instance.is_superuser and not request.user.is_superuser:
        raise PermissionDenied("Conta técnica protegida.")
    old_values = {}
    if instance.pk:
        if isinstance(instance, User):
            old_values = {field: getattr(instance, field) for field in ("role", "is_active")}
        elif isinstance(instance, Institution):
            old_values = {
                field: getattr(instance, field)
                for field in (
                    "cnpj",
                    "name",
                    "trade_name",
                    "contact_email",
                    "contact_phone",
                    "address",
                    "municipality_id",
                )
            }
        elif isinstance(instance, Program):
            old_values = {field: getattr(instance, field) for field in ("code", "name", "active")}
        elif isinstance(instance, Municipality):
            old_values = {
                field: getattr(instance, field) for field in ("ibge_code", "name", "state")
            }
    form = form_type(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if (
            isinstance(obj, User)
            and obj.pk == request.user.pk
            and (not obj.is_active or obj.role != request.user.role)
        ):
            form.add_error(None, "Não remova seu próprio acesso administrativo.")
        else:
            created = not obj.pk
            try:
                obj.save()
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
            else:
                AuditEvent.objects.create(
                    actor=request.user,
                    entity_type=model.__name__,
                    entity_id=str(obj.pk),
                    action="CREATE" if created else "UPDATE",
                    metadata={"catalog": catalog},
                )
                for field, old in old_values.items():
                    new = getattr(obj, field)
                    if old != new:
                        AuditEvent.objects.create(
                            actor=request.user,
                            entity_type=model.__name__,
                            entity_id=str(obj.pk),
                            action="FIELD_CHANGE",
                            field=field,
                            old_value=str(old),
                            new_value=str(new),
                        )
                if isinstance(obj, User) and form.cleaned_data.get("new_password"):
                    AuditEvent.objects.create(
                        actor=request.user,
                        entity_type="User",
                        entity_id=str(obj.pk),
                        action="PASSWORD_SET",
                    )
                messages.success(request, "Cadastro salvo.")
                return redirect("catalog-list", catalog=catalog)
    return render(
        request,
        "administration/form.html",
        {"form": form, "title": title, "back_url": f"/administracao/{catalog}/"},
    )


@login_required
def institution_detail(request, institution_id):
    institution = get_object_or_404(scoped_institutions(request.user), pk=institution_id)
    submissions = (
        ScopedQuerySetSelector.for_submissions(request.user)
        .filter(institution=institution)
        .select_related("edital", "municipality")
    )
    return render(
        request,
        "administration/institution.html",
        {
            "institution": institution,
            "submissions": submissions,
            "can_write": RolePermissionPolicy.can_distribute_submissions(request.user),
        },
    )
