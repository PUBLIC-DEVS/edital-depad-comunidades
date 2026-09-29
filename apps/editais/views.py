from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy, require_role
from apps.audit.models import AuditEvent

from .forms import (
    ClassificationPolicyForm,
    CloneEditalForm,
    EditalForm,
    FundingRuleForm,
    ProgramMunicipalityForm,
    RequirementCheckForm,
    RequirementForm,
    TargetGroupForm,
)
from .models import (
    ClassificationPolicy,
    Edital,
    FundingRule,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
    TargetGroup,
)
from .services import EditalConfigurationService

SECTIONS = {
    "grupos": (TargetGroup, TargetGroupForm, "Grupos / públicos"),
    "requisitos": (Requirement, RequirementForm, "Requisitos"),
    "subcriterios": (RequirementCheck, RequirementCheckForm, "Subcritérios"),
    "financeiro": (FundingRule, FundingRuleForm, "Regras financeiras"),
    "programas": (ProgramMunicipality, ProgramMunicipalityForm, "Municípios / programas"),
    "classificacao": (ClassificationPolicy, ClassificationPolicyForm, "Política de classificação"),
}


def section_objects(edital, section):
    if section not in SECTIONS:
        from django.http import Http404

        raise Http404
    model = SECTIONS[section][0]
    return model.objects.filter(
        **({"requirement__edital": edital} if model is RequirementCheck else {"edital": edital})
    )


@login_required
@require_role(User.Role.ADMINISTRADOR, User.Role.COORDENADOR)
def edital_list(request):
    return render(
        request,
        "editais/list.html",
        {
            "editais": Edital.objects.all(),
            "can_configure": RolePermissionPolicy.can_manage_editais_and_rules(request.user),
        },
    )


@login_required
@require_role(User.Role.ADMINISTRADOR)
def edital_form(request, edital_id=None):
    edital = get_object_or_404(Edital, pk=edital_id) if edital_id else Edital()
    if not edital.configuration_editable:
        raise PermissionDenied("Configuração publicada protegida; duplique o edital.")
    form = EditalForm(request.POST or None, instance=edital)
    if request.method == "POST" and form.is_valid():
        try:
            edital = EditalConfigurationService.save(form.save(commit=False), request.user)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            return redirect("edital-detail", edital_id=edital.pk)
    return render(
        request,
        "administration/form.html",
        {
            "form": form,
            "title": "Editar edital" if edital_id else "Novo edital",
            "back_url": "/admin-editais/",
        },
    )


@login_required
@require_role(User.Role.ADMINISTRADOR, User.Role.COORDENADOR)
def edital_detail(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    validation = EditalConfigurationService.validate(edital)
    return render(
        request,
        "editais/detail.html",
        {
            "edital": edital,
            "validation": validation,
            "sections": [(key, value[2]) for key, value in SECTIONS.items()],
            "can_configure": RolePermissionPolicy.can_manage_editais_and_rules(request.user),
            "events": AuditEvent.objects.filter(entity_type="Edital", entity_id=str(edital.pk))[
                :20
            ],
        },
    )


@login_required
@require_role(User.Role.ADMINISTRADOR, User.Role.COORDENADOR)
def section_list(request, edital_id, section):
    edital = get_object_or_404(Edital, pk=edital_id)
    objects = section_objects(edital, section)
    return render(
        request,
        "editais/section.html",
        {
            "edital": edital,
            "section": section,
            "title": SECTIONS[section][2],
            "objects": objects,
            "can_configure": RolePermissionPolicy.can_manage_editais_and_rules(request.user)
            and edital.configuration_editable,
        },
    )


@login_required
@require_role(User.Role.ADMINISTRADOR)
def section_form(request, edital_id, section, object_id=None):
    edital = get_object_or_404(Edital, pk=edital_id)
    qs = section_objects(edital, section)
    model, form_class, title = SECTIONS[section]
    if not edital.configuration_editable:
        raise PermissionDenied("Configuração publicada protegida.")
    instance = get_object_or_404(qs, pk=object_id) if object_id else model()
    if model is not RequirementCheck:
        instance.edital = edital
    kwargs = {"edital": edital} if model is RequirementCheck else {}
    form = form_class(request.POST or None, instance=instance, **kwargs)
    if model is RequirementCheck and not object_id:
        form.initial["requirement"] = request.GET.get("requirement")
    if request.method == "POST" and form.is_valid():
        try:
            EditalConfigurationService.save(form.save(commit=False), request.user)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            return redirect("edital-section", edital_id=edital.pk, section=section)
    return render(
        request,
        "administration/form.html",
        {
            "edital": edital,
            "form": form,
            "title": title,
            "back_url": f"/admin-editais/{edital.pk}/{section}/",
        },
    )


@login_required
@require_role(User.Role.ADMINISTRADOR)
@require_POST
def section_action(request, edital_id, section, object_id, action):
    edital = get_object_or_404(Edital, pk=edital_id)
    obj = get_object_or_404(section_objects(edital, section), pk=object_id)
    try:
        if action == "remover" and isinstance(obj, (FundingRule, ClassificationPolicy)):
            if not edital.configuration_editable:
                raise ValidationError("Configuração publicada protegida.")
            entity_id = str(obj.pk)
            obj.delete()
            AuditEvent.objects.create(
                actor=request.user,
                entity_type=type(obj).__name__,
                entity_id=entity_id,
                action="CONFIG_DELETE",
                metadata={"edital_id": edital.pk},
            )
        elif action == "desativar" and hasattr(obj, "active"):
            obj.active = False
            EditalConfigurationService.save(obj, request.user)
        elif action in {"up", "down"} and isinstance(obj, (Requirement, RequirementCheck)):
            EditalConfigurationService.reorder(obj, action, request.user)
        else:
            raise ValidationError("Operação inválida.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("edital-section", edital_id=edital.pk, section=section)


@login_required
@require_role(User.Role.ADMINISTRADOR)
@require_POST
def edital_publish(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    try:
        EditalConfigurationService.publish(edital, request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Edital publicado. Configuração e versão preservadas.")
    return redirect("edital-detail", edital_id=edital.pk)


@login_required
@require_role(User.Role.ADMINISTRADOR)
def edital_clone(request, edital_id):
    source = get_object_or_404(Edital, pk=edital_id)
    form = CloneEditalForm(
        request.POST or None,
        initial={
            "name": source.name,
            "year": source.year + 1,
            "rules_version": "1.0",
            "opens_at": source.opens_at,
            "closes_at": source.closes_at,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            clone = EditalConfigurationService.clone(source, request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            return redirect("edital-detail", edital_id=clone.pk)
    return render(
        request,
        "administration/form.html",
        {
            "form": form,
            "title": f"Duplicar configuração de {source.number}/{source.year}",
            "back_url": f"/admin-editais/{source.pk}/",
            "help_text": "A cópia terá somente configuração. Informe uma nova identidade e versão; processos e decisões permanecem no edital de origem.",
        },
    )


@login_required
@require_role(User.Role.ADMINISTRADOR)
@require_POST
def edital_status(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    try:
        EditalConfigurationService.set_status(edital, request.POST.get("status"), request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("edital-detail", edital_id=edital.pk)
