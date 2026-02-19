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
import requests
from requests.adapters import HTTPAdapter
import urllib3

try:
    from urllib3.util.retry import Retry
except ImportError:
    Retry = None

_session = None
_last_request_time = 0


def _get_session():
    """Create a requests Session with retry strategy from current settings."""
    global _session
    if _session is not None:
        return _session

    from algotik_tse.settings import settings

    _session = requests.Session()
    _session.headers.update(settings.headers)

    if Retry is not None:
        try:
            retry_strategy = Retry(
                total=settings.max_retries,
                backoff_factor=settings.retry_backoff_factor,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            _session.mount("http://", adapter)
            _session.mount("https://", adapter)
        except Exception:
            pass  # Fallback to default session without retry

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
    global _last_request_time
    from algotik_tse.settings import settings

    # Rate limiting: ensure minimum delay between consecutive requests
    if settings.rate_limit_delay > 0:
        elapsed = time.time() - _last_request_time
        if elapsed < settings.rate_limit_delay:
            time.sleep(settings.rate_limit_delay - elapsed)

    # Apply defaults from settings (caller can override any of these)
    kwargs.setdefault("headers", settings.headers)
    kwargs.setdefault("timeout", settings.timeout)
    kwargs.setdefault("verify", settings.ssl_verify)

    # Suppress SSL warnings when verification is disabled
    if not kwargs.get("verify", True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = _get_session()
    response = session.get(url, **kwargs)
    _last_request_time = time.time()
    return response


def reset_session():
    """Reset the HTTP session.

    Call this after changing retry-related settings (``max_retries``,
    ``retry_backoff_factor``) to rebuild the session with new values.
    Changes to ``ssl_verify``, ``timeout``, and ``rate_limit_delay``
    take effect immediately without needing a reset.
    """
    global _session
    if _session is not None:
        try:
            _session.close()
        except Exception:
            pass
    _session = None
