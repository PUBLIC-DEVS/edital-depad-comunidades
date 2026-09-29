"""Synthetic importer round-trip only; does not establish real workbook parity."""

import pytest
from django.core.management import call_command

from apps.editais.models import Edital
from apps.submissions.models import Assignment, Submission
from apps.submissions.services.legacy_generator import generate_synthetic_legacy_workbook


@pytest.mark.legacy
@pytest.mark.django_db
class TestSyntheticLegacyImporter:
    @pytest.fixture
    def synthetic_excel(self, tmp_path):
        excel_path = tmp_path / "edital_legado_282_processos.xlsx"
        generate_synthetic_legacy_workbook(str(excel_path))
        return str(excel_path)

    def test_synthetic_import_counts(self, synthetic_excel):
        """Verifica os números explicitamente gerados nesta fixture sintética:

        Total = 282
        G1 = 9
        G2 = 34 (PRONASCI)
        G3 = 212
        Sem Grupo = 27
        """
        # Executa comando de importação
        call_command(
            "import_legacy_edital", synthetic_excel, "--edital-number", "1", "--edital-year", 2026
        )

        edital = Edital.objects.get(number="1", year=2026)
        subs = Submission.objects.filter(edital=edital)

        # 1. Total de Processos
        assert subs.count() == 282

        # 2. Grupo 1 (Mulheres e Mães Nutrizes)
        g1_count = subs.filter(target_group=Submission.TargetGroup.G1).count()
        assert g1_count == 9, f"Esperado 9 no G1, obtido {g1_count}"

        # 3. Grupo 2 (Municípios prioritários PRONASCI)
        g2_count = subs.filter(target_group=Submission.TargetGroup.G2).count()
        assert g2_count == 34, f"Esperado 34 no G2, obtido {g2_count}"

        # 4. Grupo 3 (Demais municípios)
        g3_count = subs.filter(target_group=Submission.TargetGroup.G3).count()
        assert g3_count == 212, f"Esperado 212 no G3, obtido {g3_count}"

        # 5. Sem Grupo (Vagas zeradas / pendentes)
        sem_grupo_count = subs.filter(target_group=Submission.TargetGroup.SEM_GRUPO).count()
        assert sem_grupo_count == 27, f"Esperado 27 sem grupo, obtido {sem_grupo_count}"

        # 6. Soma exata
        assert g1_count + g2_count + g3_count + sem_grupo_count == 282

        # 7. Atribuições criadas para analistas
        active_assignments = Assignment.objects.filter(submission__edital=edital)
        assert active_assignments.count() > 0

    def test_legacy_import_idempotency(self, synthetic_excel):
        """Garante que rodar o importador duas vezes não duplica nenhum registro."""
        # 1ª Execução
        call_command("import_legacy_edital", synthetic_excel)
        first_subs_count = Submission.objects.count()
        first_assign_count = Assignment.objects.count()
        assert first_subs_count == 282

        # 2ª Execução consecutiva
        call_command("import_legacy_edital", synthetic_excel)
        second_subs_count = Submission.objects.count()
        second_assign_count = Assignment.objects.count()

        # Deve ser estritamente idempotente
        assert second_subs_count == first_subs_count
        assert second_assign_count == first_assign_count
