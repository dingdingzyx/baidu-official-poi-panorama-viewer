# Changelog

## 1.1.0 - 2026-07-15

- Aligned the query length, status messages, and manual pagination limit with the documented Place Search contract, allowing up to 400 explicitly paged results.
- Prevented edited search inputs from being combined with an existing page number and added memory-only page caching to avoid duplicate back-navigation requests.
- Preserved pagination when malformed official result items are safely filtered from a full response page.
- Added clearer selected-place and accessibility states, a same-origin resource policy, Python 3.13/3.14 CI coverage, and GitHub maintenance templates.
- Simplified the public ignore and source-distribution rules and moved package versioning to one source of truth.

## 1.0.1 - 2026-07-14

- Tightened local POST authorization so `Origin` must match the loopback request host and port exactly.
- Made the search controls a semantic form, including Enter submission from either input, and added an in-app data-flow notice.
- Added regression coverage for same-host cross-port rejection and release-surface checks for the form and notice.
- Added manual CI dispatch and cancellation of superseded runs.

## 1.0.0 - 2026-07-13

- Released a loopback-only viewer using documented Baidu Place and JavaScript Panorama APIs.
- Defined a display-only public boundary without batch collection, result persistence, downloads, or panorama-ID output.
- Added separate Server AK and Browser AK configuration, local counter-only daily budget guards, serial Place API calls, and explicit-POI panorama display.
- Added release documentation for IP/Referer allowlists, Panorama advanced permission, official API status codes, security boundaries, CI, and offline tests.
