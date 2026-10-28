"""Same production backup/recovery checks, real native TLS services + Chrome."""
import os

import pytest

from infra.acceptance.native_lab import laboratory as native_laboratory
from .test_service_recovery_integration import test_service_backup_restore_https_flow as recovery_flow


@pytest.fixture(scope="module")
def post_a5_lab(tmp_path_factory):
    if os.environ.get("DPR_POST_A5_ACCEPTANCE")!="1":pytest.skip("Enable dedicated native post-A5 acceptance explicitly")
    with native_laboratory(tmp_path_factory.mktemp("post-a5-acceptance")) as lab:
        lab["browser_acceptance"]=True
        yield lab


def test_post_a5_real_tls_backup_restore_and_browser(post_a5_lab,monkeypatch):
    recovery_flow(post_a5_lab,monkeypatch)
