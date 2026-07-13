# Contributing

This repository is an official-API local viewer, not a collection or export project.

## Scope

- Keep requests limited to documented Baidu Map APIs and their approved display flow.
- Do not add crawlers, HTML scraping, proxy rotation, bulk enumeration, batch downloads, result persistence, panorama-ID export, or high-concurrency modes.
- Do not commit API keys, cookies, account data, raw API responses, POI collections, screenshots containing credentials, or local usage ledgers.
- Preserve loopback-only binding, fixed official endpoint selection, origin checks, and serial Place API requests.

## Local checks

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check wmx.py official_viewer official_tests
python -m ruff format --check wmx.py official_viewer official_tests
python -m unittest discover -s official_tests -v
python -m build
```

Tests must be deterministic and offline. A pull request must not require a maintainer's AK, account, quota, or live map response to pass.

## Pull requests

- Explain any user-visible API-call or quota effect.
- Add focused tests for changed behavior and security boundaries.
- Keep Browser AK handling compatible with strict Referer allowlists; Server AKs must never reach the browser or logs.
- Update README and `docs/` when an official API contract or data boundary changes.
