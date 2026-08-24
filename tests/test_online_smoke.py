"""Small opt-in provider smoke; excluded from the default release gate."""

import pytest

from algotik_tse.http_client import safe_get
from algotik_tse.settings import settings

pytestmark = pytest.mark.online


def test_tsetmc_https_endpoint_responds_within_bound():
    response = safe_get(settings.url_market_watch_init, timeout=15)
    assert response.status_code == 200
    assert response.url.startswith("https://")
