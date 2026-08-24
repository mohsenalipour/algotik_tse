import pytest
import requests

import algotik_tse as att
from algotik_tse import http_client
from algotik_tse.settings import Settings, settings


class Response:
    def __init__(self, status_code=200, location=None):
        self.status_code = status_code
        self.headers = {} if location is None else {"Location": location}


class Session:
    def __init__(self, responses=None):
        self.responses = list(responses or [Response()])
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def no_rate_delay(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_delay", 0)
    monkeypatch.setattr(http_client, "_next_request_time", 0.0)


def test_legacy_introduction_raises_before_resolver_or_network(monkeypatch):
    import algotik_tse.core.stock_detail as detail

    monkeypatch.setattr(detail, "search_stock", lambda *a, **k: pytest.fail("resolved"))
    monkeypatch.setattr(detail, "safe_get", lambda *a, **k: pytest.fail("network"))
    for function in (att.get_introduction, att.stock_introduction):
        with pytest.raises(att.UnsupportedDataSourceError, match="outside"):
            function("فملی", ins_code="35425587644337450", stock="فملی")


def test_codal_runtime_apis_and_settings_are_not_public():
    configured = Settings()
    assert not hasattr(att, "get_codal_disclosures")
    assert not hasattr(att, "get_codal_disclosures_history")
    assert not any("codal" in name.lower() for name in vars(configured))


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/data",
        "https://tsetmc.com.evil.example/data",
        "https://user@cdn.tsetmc.com/data",
        "ftp://cdn.tsetmc.com/data",
        "https://codal.ir/data",
        "https://api.codal.ir/data",
        "https://codal.ir.evil.example/data",
        "https://cdn.tsetmc.com/api/Codal/GetPreparedData/1",
        "https://cdn.tsetmc.com/API/CODAL/GetPreparedData/1",
        "https://cdn.tsetmc.com/api/%43odal/GetPreparedData/1",
        "https://cdn.tsetmc.com//api//Codal/GetPreparedData/1",
        "https://cdn.tsetmc.com/api/%2543odal/Get/1",
        "https://cdn.tsetmc.com/%2561pi/Codal/Get/1",
        "https://cdn.tsetmc.com/foo/../api/Codal/Get/1",
        "https://cdn.tsetmc.com/api/%2e%2e/api/Codal/Get/1",
        "https://cdn.tsetmc.com/api\\Codal\\Get\\1",
        "https://cdn.tsetmc.com/api/%2525252543odal/Get/1",
        "https://cdn.tsetmc.com/api/%ZZ/Codal/Get/1",
        "https://cdn.tsetmc.com/api/%/Codal/Get/1",
    ],
)
def test_unsupported_destinations_fail_before_sleep_or_session(monkeypatch, url):
    monkeypatch.setattr(http_client.time, "sleep", lambda _: pytest.fail("slept"))
    monkeypatch.setattr(
        http_client.requests, "Session", lambda: pytest.fail("session created")
    )
    monkeypatch.setattr(http_client, "_session", None)
    with pytest.raises(att.UnsupportedDataSourceError):
        http_client.safe_get(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.tsetmc.com/api/ClosingPrice/GetPriceAdjustList/1",
        "https://old.tsetmc.com/test",
        "https://ifb.ir/ytm.aspx",
        "https://api.tgju.org/test",
    ],
)
def test_supported_provider_domains_are_exact_or_subdomain(monkeypatch, url):
    fake = Session()
    monkeypatch.setattr(http_client, "_session", fake)
    result = http_client.safe_get(url, params={"a": "b"}, timeout=2)
    assert result.status_code == 200
    assert fake.calls[0][0] == url
    assert fake.calls[0][1]["params"] == {"a": "b"}
    assert fake.calls[0][1]["timeout"] == 2
    assert fake.calls[0][1]["allow_redirects"] is False


def test_every_configured_http_endpoint_is_within_boundary():
    configured = Settings()
    urls = [
        value
        for value in vars(configured).values()
        if isinstance(value, str) and value.lower().startswith(("http://", "https://"))
    ]
    assert urls
    for url in urls:
        assert http_client._validate_outbound_url(url) == url


def test_relative_redirect_is_joined_and_each_hop_is_validated(monkeypatch):
    fake = Session([Response(302, "/next"), Response(200)])
    monkeypatch.setattr(http_client, "_session", fake)
    response = http_client.safe_get("https://cdn.tsetmc.com/start", headers={"X": "1"})
    assert response.status_code == 200
    assert [call[0] for call in fake.calls] == [
        "https://cdn.tsetmc.com/start",
        "https://cdn.tsetmc.com/next",
    ]
    assert all(call[1]["headers"] == {"X": "1"} for call in fake.calls)


@pytest.mark.parametrize(
    "destination",
    [
        "https://api.tgju.org/steal",
        "https://ifb.ir/steal",
        "https://old.tsetmc.com/steal",
        "http://cdn.tsetmc.com/steal",
        "https://cdn.tsetmc.com:444/steal",
    ],
)
def test_cross_origin_redirect_never_leaks_headers_or_params(monkeypatch, destination):
    fake = Session([Response(302, destination)])
    monkeypatch.setattr(http_client, "_session", fake)
    with pytest.raises(att.UnsupportedDataSourceError, match="cross-origin"):
        http_client.safe_get(
            "https://cdn.tsetmc.com/start",
            headers={"Authorization": "Bearer secret"},
            params={"token": "secret"},
        )
    assert len(fake.calls) == 1
    assert fake.calls[0][1]["headers"] == {"Authorization": "Bearer secret"}
    assert fake.calls[0][1]["params"] == {"token": "secret"}


def test_same_origin_redirect_uses_location_query_without_original_params(monkeypatch):
    fake = Session([Response(302, "/next?server=1"), Response(200)])
    monkeypatch.setattr(http_client, "_session", fake)
    response = http_client.safe_get(
        "https://cdn.tsetmc.com/start",
        params={"original": "must-not-repeat"},
    )
    assert response.status_code == 200
    assert fake.calls[0][1]["params"] == {"original": "must-not-repeat"}
    assert fake.calls[1][0] == "https://cdn.tsetmc.com/next?server=1"
    assert "params" not in fake.calls[1][1]


def test_cross_provider_redirect_is_rejected_before_second_request(monkeypatch):
    fake = Session([Response(302, "https://example.com/steal")])
    monkeypatch.setattr(http_client, "_session", fake)
    with pytest.raises(att.UnsupportedDataSourceError):
        http_client.safe_get("https://cdn.tsetmc.com/start")
    assert len(fake.calls) == 1


def test_codal_redirect_on_tsetmc_host_is_rejected(monkeypatch):
    fake = Session([Response(302, "/api/Codal/GetPreparedData/1")])
    monkeypatch.setattr(http_client, "_session", fake)
    with pytest.raises(att.UnsupportedDataSourceError, match="Codal"):
        http_client.safe_get("https://cdn.tsetmc.com/start")
    assert len(fake.calls) == 1


def test_redirect_loop_and_hop_limit_are_bounded(monkeypatch):
    fake = Session([Response(302, "/start")])
    monkeypatch.setattr(http_client, "_session", fake)
    with pytest.raises(requests.exceptions.TooManyRedirects, match="loop"):
        http_client.safe_get("https://cdn.tsetmc.com/start")

    fake = Session([Response(302, "/one")])
    monkeypatch.setattr(http_client, "_session", fake)
    with pytest.raises(requests.exceptions.TooManyRedirects, match="exceeded"):
        http_client.safe_get("https://cdn.tsetmc.com/start", max_redirects=0)


def test_allow_redirects_false_preserves_original_response(monkeypatch):
    fake = Session([Response(302, "https://example.com/steal")])
    monkeypatch.setattr(http_client, "_session", fake)
    response = http_client.safe_get(
        "https://cdn.tsetmc.com/start", allow_redirects=False
    )
    assert response.status_code == 302
    assert len(fake.calls) == 1
