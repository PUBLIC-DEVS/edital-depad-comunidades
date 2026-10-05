from io import StringIO

import pytest
from django.core.management import call_command

from apps.ranking.models import RankingSnapshot
from apps.submissions.models import Submission
from apps.submissions.services.funding import FundingService

pytestmark = pytest.mark.django_db


def test_demo_command_uses_financial_and_ranking_services_without_duplicate_snapshot():
    call_command("seed_demo", stdout=StringIO())
    for sub in Submission.objects.all():
        assert (
            sub.valor_global,
            sub.patrimonio_minimo,
        ) == FundingService.calculate_submission_values(sub)
    snapshot = RankingSnapshot.objects.get()
    assert all(
        e.qualification_status in ("ELIGIBLE_FOR_RANKING", "RANKED") for e in snapshot.entries.all()
    )
    before = Submission.objects.count()
    call_command("seed_demo", stdout=StringIO())
    assert Submission.objects.count() == before
    assert RankingSnapshot.objects.count() == 1
