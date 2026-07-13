## Summary

## Verification

- [ ] `python -m ruff check wmx.py official_viewer official_tests`
- [ ] `python -m ruff format --check wmx.py official_viewer official_tests`
- [ ] `python -m unittest discover -s official_tests -v`
- [ ] `python -m build`

## Official API and security boundary

- [ ] This change uses only documented official APIs and does not add scraping, bulk enumeration, proxying, retries, or high-concurrency behavior.
- [ ] This change does not expose Server AKs, commit credentials, persist POI/API payloads, or export panorama IDs.
- [ ] I documented any change to request volume, daily budget behavior, Browser Referer handling, or Server IP handling.
