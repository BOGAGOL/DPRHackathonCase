from infra.targets import MIGRATION_DATASETS, MIGRATION_PAIRS, PROTECTED_DATABASES, READ_ONLY_SOURCES
from infra.protected.apply import DATABASES
from migration.connection import TARGETS
from migration.runner import check_pair
from migration.model import MigrationError
import pytest


def test_shared_allowlists_are_consistent_and_never_target_plaintext_sources():
    assert set(MIGRATION_PAIRS)==set(READ_ONLY_SOURCES)
    assert set(MIGRATION_PAIRS.values())==set(PROTECTED_DATABASES)==set(DATABASES)
    assert set(PROTECTED_DATABASES).isdisjoint(READ_ONLY_SOURCES)
    assert len(set(MIGRATION_PAIRS.values()))==len(MIGRATION_PAIRS)
    assert MIGRATION_DATASETS["baseline_1m"]["expected_rows"]==1000000
    assert TARGETS["port"]==5433 and TARGETS["sslmode"]=="verify-full"
    check_pair("baseline_1m","protected_1m")
    for source,target in (("baseline_1m","postgres"),("baseline_1m","protected_100k"),("baseline_100k","protected_1m")):
        with pytest.raises(MigrationError):check_pair(source,target)
