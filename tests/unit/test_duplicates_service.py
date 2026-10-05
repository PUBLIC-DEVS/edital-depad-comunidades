import pytest
from django.utils import timezone

from apps.editais.models import Edital
from apps.institutions.models import Institution, Municipality
from apps.submissions.models import Submission
from apps.submissions.services import DuplicateService


@pytest.mark.django_db
class TestDuplicateService:
    @pytest.fixture
    def setup_data(self):
        mun = Municipality.objects.create(ibge_code="3106200", name="Belo Horizonte", state="MG")
        inst = Institution.objects.create(
            cnpj="00000000000191", name="Instituto Minas", municipality=mun
        )
        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital Duplicidades",
            number="03",
            year=2024,
            opens_at=now,
            closes_at=now + timezone.timedelta(days=30),
        )
        return {"mun": mun, "inst": inst, "edital": edital, "now": now}

    def test_keep_earliest_submission_policy(self, setup_data):
        now = setup_data["now"]
        sub1 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.001",
            received_at=now - timezone.timedelta(hours=2),
            municipality=setup_data["mun"],
        )
        sub2 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.002",
            received_at=now - timezone.timedelta(hours=1),
            municipality=setup_data["mun"],
        )

        resolution = DuplicateService.resolve_duplicates(
            [sub1, sub2],
            policy=Edital.DuplicatePolicy.KEEP_EARLIEST_SUBMISSION,
        )
        assert sub1 in resolution.retained
        assert sub2 in resolution.suppressed
        assert sub2.id in resolution.suppression_reasons

    def test_keep_latest_submission_policy(self, setup_data):
        now = setup_data["now"]
        sub1 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.001",
            received_at=now - timezone.timedelta(hours=2),
            municipality=setup_data["mun"],
        )
        sub2 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.002",
            received_at=now - timezone.timedelta(hours=1),
            municipality=setup_data["mun"],
        )

        resolution = DuplicateService.resolve_duplicates(
            [sub1, sub2],
            policy=Edital.DuplicatePolicy.KEEP_LATEST_SUBMISSION,
        )
        assert sub2 in resolution.retained
        assert sub1 in resolution.suppressed

    def test_two_submissions_same_timestamp_tie_breaker(self, setup_data):
        now = setup_data["now"]
        # Mesmo horário exato
        sub_a = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.010",
            received_at=now,
            municipality=setup_data["mun"],
        )
        sub_b = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.020",
            received_at=now,
            municipality=setup_data["mun"],
        )

        resolution = DuplicateService.resolve_duplicates(
            [sub_a, sub_b],
            policy=Edital.DuplicatePolicy.KEEP_EARLIEST_SUBMISSION,
        )
        # Menor SEI vence
        assert sub_a in resolution.retained
        assert sub_b in resolution.suppressed

    def test_cancelled_or_closed_submission_does_not_block(self, setup_data):
        now = setup_data["now"]
        sub_closed = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.001",
            received_at=now - timezone.timedelta(hours=5),
            municipality=setup_data["mun"],
            workflow_status=Submission.WorkflowStatus.CLOSED,
        )
        sub_active = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.002",
            received_at=now - timezone.timedelta(hours=1),
            municipality=setup_data["mun"],
            workflow_status=Submission.WorkflowStatus.RECEIVED,
        )

        resolution = DuplicateService.resolve_duplicates(
            [sub_closed, sub_active],
            policy=Edital.DuplicatePolicy.KEEP_EARLIEST_SUBMISSION,
        )
        # sub_active deve ser mantida (não suprimida pelo sub_closed)
        assert sub_active in resolution.retained
        assert sub_active not in resolution.suppressed

    def test_more_than_two_submissions(self, setup_data):
        now = setup_data["now"]
        subs = [
            Submission.objects.create(
                edital=setup_data["edital"],
                institution=setup_data["inst"],
                processo_sei=f"71000.00{i}",
                received_at=now - timezone.timedelta(hours=10 - i),
                municipality=setup_data["mun"],
            )
            for i in range(4)
        ]

        resolution = DuplicateService.resolve_duplicates(
            subs,
            policy=Edital.DuplicatePolicy.KEEP_EARLIEST_SUBMISSION,
        )
        # Mais antiga é subs[0]
        assert resolution.retained == [subs[0]]
        assert len(resolution.suppressed) == 3
        for loser in subs[1:]:
            assert loser in resolution.suppressed
