=======
History
=======

1.2.0 (2026-09-01)
------------------

* Added a complete industry-index API: exact constituent lists, live industry
  snapshots, daily index history, short constituent history, intraday candles,
  and configurable industry rankings.
* Joined index membership to bulk MarketWatch, client-type, and optional
  order-book feeds by exact ``InsCode`` while exposing freshness and coverage.
* Added an in-memory membership cache with configurable TTL and explicit refresh
  controls to avoid repeated ``GetIndexCompany`` requests.
* Documented overlapping industry memberships, empty industry indices,
  survivorship bias in current-member history, estimated client flow, and the
  absence of official constituent weights and synthetic index volume.
* Corrected the legacy ``list_indices()`` mapping: ``Change`` is now the point
  move and ``ChangePct`` is the percentage move.
* Expanded the Persian README and the linked, RTL PDF guide for the new industry
  workflow and its complete public contracts.

1.1.3 (2026-08-28)
------------------
* Replaced the cached dynamic PyPI version badge with an explicit 1.1.3 badge
  so the displayed release always matches the documentation release.
* Rebuilt the bilingual PDF user guide from the current README with the
  official AlgoTik logo, clickable internal navigation, improved RTL layout,
  clearer tables, code samples and print readability.

1.1.2 (2026-08-28)
------------------
* Redesigned the primary README around ordinary user workflows, with a
  prominent quick API map and a separate detailed reference layer.
* Added per-function input and option guidance beside the most-used APIs,
  including defaults, accepted values, outputs and important behavior.
* Preserved complete documentation coverage for all public exports, legacy
  aliases, data contracts and the analytical APIs introduced in 1.1.0.

1.1.1 (2026-08-25)
------------------
* Improved the unified README presentation for Persian readers with an
  explicit right-to-left container while preserving Markdown examples and
  API contracts.
* Restored the complete project badge set: PyPI version, supported Python
  versions, total downloads, PyPI license and pre-commit.ci status.

1.1.0 (2026-08-24)
------------------
* Added live/history symmetry for prices and حقیقی/حقوقی data, including an
  opt-in ``include_today=True`` live row with explicit source and freshness.
* Added reconstructed five-level order-book and queue history, live market
  watcher/events, breadth, sector flow, market messages and state changes.
* Added opt-in SQLite market/event snapshot history. Coverage starts when the
  user records data; the package does not claim historical backfill.
* Added exact ``InstrumentRef``/``InsCode`` resolution with explicit ambiguity
  errors, live and historical individual trades, same-snapshot EPS/P/E
  fundamentals, and an exact-identity listed-funds view.
* Added TSETMC price-adjustment history and latest-event helpers. Raw corporate
  type codes are retained, while price discontinuities are never inferred to
  be confirmed cash dividends.
* Added Iranian treasury analytics (effective/simple yields, duration,
  convexity, DV01), IFB reference parsing and current/historical yield curves.
* Added professional European Black--Scholes option analytics: IV by quote
  side, unit-labelled Greeks, parity diagnostics, PCR/liquidity and explicit
  user-saved option snapshot history.
* Preserved 1.0.x public defaults and aliases; all new behavior is additive or
  opt-in.
* Enforced the supported-source boundary at the final HTTP layer, including
  redirect origin pinning. Legacy company-introduction imports remain present
  but now fail explicitly before resolution or network access because their
  former data source is outside the package boundary.
* Hardened transport defaults: HTTPS TSETMC endpoints, certificate verification
  enabled by default and thread-safe rate limiting/session reset. Calendar-
  sensitive computations now share the Tehran-aware clock helper.
* Added offline-first CI through Python 3.14, bounded online tests, release
  metadata and artifact checks.

1.0.3 (2026-07-12)
------------------
* Added ``search_stock_symbol()`` helper for canonical TSETMC symbol spelling,
  including Persian/Arabic character normalization.

1.0.2 (2026-03-24)
------------------
* Expanded industry index support from 11 to 44 sectors — all TSETMC industry indices are now supported.
* Added Arabic/Persian character normalization for index name matching (ي/ی, ك/ک).
* Added ``list_indices()`` — get all market indices with current values.
* Added ``get_index_companies()`` — get companies belonging to a specific index.
* Users can now query any industry index by name variants (e.g. ``'بانک'``, ``'شاخص بانک'``, ``'شاخص صنعت بانکها'``).

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
-------------------
* tenth release on PyPI.
* bug fix in currency, dollar sana and nima buy and sell.

0.3.11 (2024-03-15)
-------------------
* eleventh release on PyPI.
* add a few index of industry to package.

0.3.12 (2024-12-07)
-------------------
* Twelfth release on PyPI.
* fix stock list error.
