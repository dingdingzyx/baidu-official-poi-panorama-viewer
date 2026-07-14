# Changelog

## 1.0.1 - 2026-07-14

- Tightened local POST authorization so `Origin` must match the loopback request host and port exactly.
- Made the search controls a semantic form, including Enter submission from either input, and added an in-app data-flow notice.
- Added regression coverage for same-host cross-port rejection and release-surface checks for the form and notice.
- Added manual CI dispatch and cancellation of superseded runs.

## 1.0.0 - 2026-07-13

- Replaced the previous non-official collection workflow with a loopback-only viewer using documented Baidu Place and JavaScript Panorama APIs.
- Removed public batch collection, result persistence, resume, downloads, panorama-ID output, and high-concurrency controls from the release surface.
- Added separate Server AK and Browser AK configuration, local counter-only daily budget guards, serial Place API calls, and explicit-POI panorama display.
- Added release documentation for IP/Referer allowlists, Panorama advanced permission, official API status codes, security boundaries, CI, and offline tests.
