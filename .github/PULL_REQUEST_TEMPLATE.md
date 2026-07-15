## What changed

Describe the user-visible behavior and any effect on official API calls or local quota counters.

## Verification

- [ ] `python -m ruff check wmx.py official_viewer official_tests`
- [ ] `python -m ruff format --check wmx.py official_viewer official_tests`
- [ ] `python -m unittest discover -s official_tests -v`
- [ ] `python -m build`
- [ ] Documentation reflects changed API or data boundaries.
- [ ] No AK, `.env`, raw API response, POI collection, panorama ID, or runtime ledger is included.

## Official API boundary

- [ ] This change uses documented official APIs and does not add scraping, automatic page traversal, proxying, retries, or high-concurrency behavior.
- [ ] Server AKs remain in Python, POI page reuse remains memory-only, and panorama IDs are neither rendered nor persisted.
