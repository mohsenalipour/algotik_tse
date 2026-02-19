=======
History
=======

1.0.1 (2026-02-19)
------------------
* Added ``lxml`` and ``openpyxl`` to install requirements.
* Fixed ``NAV_Discount`` column dtype bug in ``list_etfs()`` — was ``object`` (due to ``None`` init), now correctly ``float64``.

1.0.0 (2025-07-12)
------------------
* **Major release** — Production/Stable.
* New centralized HTTP client with retry, timeout, and rate-limiting support.
* Added configurable ``settings`` object (``ssl_verify``, ``timeout``, ``max_retries``, ``retry_backoff_factor``, ``rate_limit_delay``).
* Custom exception hierarchy (``AlgotikTSEError``, ``ConnectionError``, ``StockNotFoundError``, ``InvalidParameterError``, ``DataParsingError``, ``RateLimitError``).
* Replaced all bare ``except:`` blocks with specific exception handling.
* Fixed ``None`` check bugs in ``stockdetail``, ``stock_information``, ``stock_statistics``, ``shareholders``.
* Eliminated ~200 lines of duplicated code via shared helper functions (``add_date_columns``, ``apply_date_format``, ``apply_return_type``, ``filter_by_date_or_values``).
* Settings singleton — no more redundant ``Settings()`` instantiation per call.
* Comprehensive professional README with full API reference.
* Added ``numpy`` to install requirements.
* Updated classifiers to ``Development Status :: 5 - Production/Stable``.

0.2.8 (2023-12-17)
------------------

* First release on PyPI.


0.2.9 (2023-12-18)
------------------
* Second release on PyPI.
* fix bug in returns


0.3.2 (2024-01-05)
------------------
* Third release on PyPI.
* Add Shareholders

0.3.3 (2024-01-05)
------------------
* Third release on PyPI.
* Fix bug in change_amount of shareholders

0.3.4 (2024-01-11)
------------------
* Fourth release on PyPI.
* Add Capital Increase in simple method

0.3.5 (2024-01-18)
------------------
* Fifth release on PyPI.
* Add stock information in beta phase.

0.3.6 (2024-02-02)
------------------
* sixth release on PyPI.
* Add stock statistics in beta phase.

0.3.7 (2024-02-04)
------------------
* seventh release on PyPI.
* Add currencies and coins in beta phase.

0.3.8 (2024-02-27)
------------------
* eighth release on PyPI.
* Add payeh market color in stocklist.

0.3.9 (2024-03-08)
------------------
* ninth release on PyPI.
* bug fix in shareholders change_amount.

0.3.9 (2024-03-08)
------------------
* ninth release on PyPI.
* bug fix in shareholders change_amount.

0.3.10 (2024-03-15)
------------------
* tenth release on PyPI.
* bug fix in currency, dollar sana and nima buy and sell.

0.3.11 (2024-03-15)
------------------
* eleventh release on PyPI.
* add a few index of industry to package.

0.3.12 (2024-12-07)
------------------
* Twelfth release on PyPI.
* fix stock list error.
