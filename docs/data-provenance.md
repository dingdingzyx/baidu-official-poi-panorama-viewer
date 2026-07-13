# Data Boundary and Provenance

## Runtime sources

| Data | Source | Use | Persistence |
| --- | --- | --- | --- |
| POI page | Documented Baidu Place API | Immediate local display | No |
| Panorama scene | Documented Baidu JavaScript API | Immediate browser display after a POI click | No |
| API credentials | User-controlled environment or `.env` | Authentication only | `.env` is ignored by Git |
| Daily counters | Local viewer | Guard accidental request overuse | Date and integer counts only |

## Explicit exclusions

This public release does not include or create crawler outputs, cached API payloads, panorama IDs, POI databases, bulk address collections, historical query results, or resumable collection state.

The application is an interface to the account holder's authorized official services. It does not assert ownership of source data or guarantee that a response is complete, current, or suitable for any use beyond the applicable official terms.
