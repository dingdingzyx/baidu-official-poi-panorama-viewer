# Security Policy

## Supported version

Security fixes target the current `1.x` release line.

## Credential handling

- Never publish `BAIDU_MAP_SERVER_AK`, `BAIDU_MAP_BROWSER_AK`, `.env`, browser storage, cookies, or complete API responses.
- Treat a leaked Server AK as compromised: rotate it in the Baidu Map Open Platform console and tighten its IP allowlist.
- Browser AKs are visible to browsers by design. Restrict their Referer allowlist to controlled origins and rotate them when an unintended origin was authorized.
- The official JavaScript API requires CSP `unsafe-eval` and inline styles at runtime. This viewer does not evaluate user data or allow inline JavaScript, and it continues to block plain-HTTP script sources.

## Reporting a vulnerability

Before the first public release, enable GitHub Private Vulnerability Reporting for the repository. Then report local-server, origin-check, credential-handling, or dependency vulnerabilities through [GitHub Security Advisories](https://github.com/dingdingzyx/baidu-official-poi-panorama-viewer/security/advisories/new).

Do not include active AKs, raw map responses, addresses, or reproduction recordings containing credentials in a public issue. If private reporting is not yet enabled, open a minimal public contact issue without sensitive material.
