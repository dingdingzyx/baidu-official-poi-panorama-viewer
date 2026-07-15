# Data Boundary and Provenance

## Runtime sources

| Data | Source | Use | Persistence |
| --- | --- | --- | --- |
| POI page and UID union | Documented Baidu Place API | Immediate display, back navigation, and loaded-page deduplication | Current browser page memory only; cleared on refresh |
| Panorama scene | Documented Baidu JavaScript API | Immediate browser display after a POI click | No |
| API credentials | User-controlled environment or `.env` | Authentication only | `.env` is ignored by Git |
| Daily counters | Local viewer | Guard accidental request overuse | Date and integer counts only |

## Explicit exclusions

This public release does not include or persist crawler outputs, cached API payloads, panorama IDs, POI databases, bulk address collections, historical query results, or resumable collection state.

The application is an interface to the account holder's authorized official services. Its 20-page/400-result hard boundary and the API's capped `total` field do not mean a city or keyword is complete. UID deduplication measures only the pages the user explicitly loaded; it does not estimate missing POIs. The project does not assert ownership of source data or guarantee that a response is complete, current, or suitable for any use beyond the applicable official terms.
