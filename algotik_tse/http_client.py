"""HTTP client with retry, timeout, rate limiting, and configurable SSL.

This module provides a `safe_get` function that wraps `requests.get` with:
- Automatic retry on transient failures (429, 500, 502, 503, 504)
- Configurable timeout (from settings.timeout)
- Rate limiting between requests (from settings.rate_limit_delay)
- Configurable SSL verification (from settings.ssl_verify)
- Connection pooling via requests.Session

All defaults are read from `algotik_tse.settings.settings` at call time,
so changes to settings take effect immediately.
"""

import time
import threading
import posixpath
import re
import requests
from urllib.parse import unquote, urljoin, urlsplit
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from algotik_tse.exceptions import UnsupportedDataSourceError

_session = None
_session_lock = threading.RLock()
_rate_lock = threading.Lock()
_next_request_time = 0.0

_ALLOWED_SOURCE_DOMAINS = ("tsetmc.com", "ifb.ir", "tgju.org")
_REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))
_DEFAULT_MAX_REDIRECTS = 5
_MAX_PERCENT_DECODE_PASSES = 4
_MALFORMED_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")


def _canonical_provider_path(path):
    """Return a routing-equivalent path or reject ambiguous encodings.

    Reverse proxies do not all decode percent escapes the same number of
    times.  Decode a small bounded number of layers, reject malformed or
    excessive nesting, normalize Windows-style separators and RFC dot
    segments, and only then apply endpoint policy.
    """
    current = path or "/"
    for _ in range(_MAX_PERCENT_DECODE_PASSES):
        if _MALFORMED_PERCENT.search(current):
            raise UnsupportedDataSourceError(
                "malformed percent escape in provider URL path"
            )
        try:
            decoded = unquote(current, errors="strict")
        except UnicodeDecodeError as exc:
            raise UnsupportedDataSourceError(
                "invalid percent-encoded provider URL path"
            ) from exc
        if decoded == current:
            break
        current = decoded
    else:
        if _PERCENT_ESCAPE.search(current):
            raise UnsupportedDataSourceError(
                "provider URL path uses excessive nested percent encoding"
            )
    if _MALFORMED_PERCENT.search(current) or "%" in current:
        raise UnsupportedDataSourceError(
            "ambiguous percent encoding in provider URL path"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in current):
        raise UnsupportedDataSourceError(
            "control characters are not allowed in URL paths"
        )
    current = current.replace("\\", "/")
    normalized = posixpath.normpath("/" + current.lstrip("/"))
    return "/" if normalized in {".", "//"} else normalized


def _url_origin(url):
    """Return a normalized (scheme, hostname, effective-port) origin tuple."""
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    default_port = 443 if scheme == "https" else 80
    return (
        scheme,
        (parsed.hostname or "").rstrip(".").lower(),
        parsed.port or default_port,
    )


def _validate_outbound_url(url):
    """Validate one destination before any wait, session creation, or I/O."""
    if not isinstance(url, str) or not url.strip():
        raise UnsupportedDataSourceError("outbound URL must be a non-empty string")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise UnsupportedDataSourceError("invalid outbound URL") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsupportedDataSourceError("only HTTP(S) provider URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise UnsupportedDataSourceError("userinfo is not allowed in provider URLs")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if hostname == "codal.ir" or hostname.endswith(".codal.ir"):
        raise UnsupportedDataSourceError(
            "Codal endpoints are outside algotik-tse's TSETMC market-data boundary"
        )
    if not any(
        hostname == root or hostname.endswith("." + root)
        for root in _ALLOWED_SOURCE_DOMAINS
    ):
        raise UnsupportedDataSourceError(
            "URL host {!r} is outside algotik-tse's supported providers".format(
                hostname
            )
        )
    # Codal remains a separate data source even when its API is proxied under
    # a TSETMC hostname.  Reject it at the final outbound boundary.
    normalized_segments = [
        segment
        for segment in _canonical_provider_path(parsed.path).lower().split("/")
        if segment
    ]
    if normalized_segments[:2] == ["api", "codal"]:
        raise UnsupportedDataSourceError(
            "Codal endpoints are outside algotik-tse's TSETMC market-data boundary"
        )
    return parsed._replace(netloc=parsed.netloc).geturl()


def _request_once(url, kwargs):
    """Perform one already-validated request with the shared rate scheduler."""
    global _next_request_time
    from algotik_tse.settings import settings

    delay = max(float(settings.rate_limit_delay), 0.0)
    with _rate_lock:
        with _session_lock:
            now = time.monotonic()
            scheduled = max(now, _next_request_time)
            while now < scheduled:
                time.sleep(scheduled - now)
                now = time.monotonic()
            _next_request_time = now + delay
            session = _get_session()
            return session.get(url, **kwargs)


def _build_retry_strategy(settings):
    """Build a GET-only retry policy across supported urllib3 APIs.

    urllib3 1.26+ uses ``allowed_methods``. The explicit compatibility branch
    supports older adapter APIs without silently disabling retry behavior.
    """

    retry_kwargs = {
        "total": settings.max_retries,
        "backoff_factor": settings.retry_backoff_factor,
        "status_forcelist": [429, 500, 502, 503, 504],
    }
    methods = frozenset(["GET"])
    try:
        return Retry(allowed_methods=methods, **retry_kwargs)
    except TypeError:
        try:
            return Retry(method_whitelist=methods, **retry_kwargs)
        except TypeError as method_whitelist_error:
            raise RuntimeError(
                "installed urllib3 does not support a compatible Retry method API"
            ) from method_whitelist_error


def _get_session():
    """Create a requests Session with retry strategy from current settings."""
    global _session
    with _session_lock:
        if _session is not None:
            return _session

        from algotik_tse.settings import settings

        session = requests.Session()
        session.headers.update(settings.headers)
        retry_strategy = _build_retry_strategy(settings)
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _session = session
        return _session


def safe_get(url, **kwargs):
    """Make a GET request with rate limiting, timeout, SSL config, and retry.

    Uses defaults from ``algotik_tse.settings.settings``. Any explicit kwarg
    passed will override the corresponding setting.

    Parameters
    ----------
    url : str
        The URL to request.
    **kwargs
        Additional keyword arguments passed to ``session.get()``.
        Common overrides: ``headers``, ``timeout``, ``verify``.

    Returns
    -------
    requests.Response
        The HTTP response object.

    Raises
    ------
    requests.exceptions.RequestException
        After all retries are exhausted.
    """
    from algotik_tse.settings import settings

    current_url = _validate_outbound_url(url)
    follow_redirects = kwargs.pop("allow_redirects", True)
    max_redirects = kwargs.pop("max_redirects", _DEFAULT_MAX_REDIRECTS)
    if not isinstance(follow_redirects, bool):
        raise TypeError("allow_redirects must be bool")
    if isinstance(max_redirects, bool) or not isinstance(max_redirects, int):
        raise TypeError("max_redirects must be a non-negative integer")
    if max_redirects < 0:
        raise ValueError("max_redirects must be a non-negative integer")

    # Apply defaults from settings (caller can override any of these)
    kwargs.setdefault("headers", settings.headers)
    kwargs.setdefault("timeout", settings.timeout)
    kwargs.setdefault("verify", settings.ssl_verify)
    # Never let requests/urllib3 cross the validated source boundary on our
    # behalf. Redirects are resolved and revalidated one hop at a time below.
    kwargs["allow_redirects"] = False

    # Lock order is rate -> session everywhere. Requests are serialized by the
    # shared Session lock, so reserving the slot immediately before the actual
    # call guarantees start-to-start spacing even when reset and queued callers
    # race. Holding the session lock through completion prevents close-in-flight.
    visited = {current_url}
    pinned_origin = _url_origin(current_url)
    for hop in range(max_redirects + 1):
        request_kwargs = dict(kwargs)
        if hop:
            # ``params`` belongs to the original request.  The redirect's
            # Location is already a complete next URL and must not inherit or
            # duplicate the caller's original query parameters.
            request_kwargs.pop("params", None)
        response = _request_once(current_url, request_kwargs)
        if (
            not follow_redirects
            or getattr(response, "status_code", None) not in _REDIRECT_STATUSES
        ):
            return response
        location = getattr(response, "headers", {}).get("Location")
        if not location:
            return response
        if hop >= max_redirects:
            raise requests.exceptions.TooManyRedirects(
                "exceeded {} validated redirects".format(max_redirects),
                response=response,
            )
        next_url = _validate_outbound_url(urljoin(current_url, location))
        if _url_origin(next_url) != pinned_origin:
            raise UnsupportedDataSourceError(
                "cross-origin redirects are not allowed for provider requests"
            )
        if next_url in visited:
            raise requests.exceptions.TooManyRedirects(
                "redirect loop detected", response=response
            )
        visited.add(next_url)
        current_url = next_url


def reset_session():
    """Reset the HTTP session.

    Call this after changing retry-related settings (``max_retries``,
    ``retry_backoff_factor``) to rebuild the session with new values.
    Changes to ``ssl_verify``, ``timeout``, and ``rate_limit_delay``
    take effect immediately without needing a reset.
    """
    global _session, _next_request_time
    # Lock order is always rate -> session when both are needed. Preserve a
    # future reservation so reset cannot erase the spacing already granted to
    # an in-flight/concurrent caller.
    with _rate_lock:
        with _session_lock:
            old_session = _session
            _session = None
            _next_request_time = max(_next_request_time, time.monotonic())
            if old_session is not None:
                old_session.close()
