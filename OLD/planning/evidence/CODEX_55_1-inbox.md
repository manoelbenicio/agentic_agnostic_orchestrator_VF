# CODEX_55#1 — ONDA3-INBOX Evidence Report
## Timestamp: 2026-06-26T20:13:23Z

## Summary
Backend inbox_api created and frontend /inbox plugged to consume real API.

## Files Created
| File | SHA256 |
|------|--------|
| AOP/control-plane/inbox_api/__init__.py | f7f69a3d89d6be0c7577db74b428f8d6e70f7778da7c7e60e5c38b7f60b86f51 |
| AOP/control-plane/inbox_api/models.py | c3f05760ba3e55bf17e4025ba8713984f56754458a5e6d338362f5295fda91c8 |
| AOP/control-plane/inbox_api/schema.py | 70c96abe74f844d3c87f21fa589b88d7437a429b67f4f31e81d8164c2835d508 |
| AOP/control-plane/inbox_api/repository.py | 8fbdc4739862a3d95ecb2154da1eb2069aac2bebf253f2de34178c3ee7b40dfb |
| AOP/control-plane/inbox_api/router.py | 4bf1e3c7114d2791e2195fad9aa931a105a7def95be7ef6ca1800996bf7f8e48 |
| AOP/control-plane/inbox_api/tests/__init__.py | 0b21dfd2261c2b0fad6cde834d093dba4f31ccb2f1ac67f5ebf184ca666e15b1 |
| AOP/control-plane/inbox_api/tests/conftest.py | 085130baa6f12be3faaf2c28700b6250df2e3a041592bb37803953023e5809ac |
| AOP/control-plane/inbox_api/tests/test_inbox_api.py | 795dc287a0e0911edfbfcb89303671efcfb6259a22e2b6bd21367dc29848dfdd |

## Files Modified
| File | SHA256 |
|------|--------|
| AOP/control-plane/app/main.py | b3ec68e8f94bd1904d2a26652c137da8d8e7834d9548fa712f71ef637bca6e6d |
| AOP/control-plane/app/dependencies.py | 948e7d14a78da16e089cb509102abd170acb63e56a301727bed55dbc0cadca22 |
| AOP/web/src/components/inbox/inbox-view.tsx | b13199ee7394448d9e02536f5856df5995a2448ac8dea33169e2824b2f681d53 |

## File Unchanged (no modification needed)
| File | SHA256 |
|------|--------|
| AOP/web/src/app/inbox/page.tsx | 42283245dd08a3d9723ebb550a656c5353f0fc9c7d2284f070085a16d949bd4c |

## Test Results

### pytest (2 passed)
```
inbox_api/tests/test_inbox_api.py::test_inbox_repository_crud PASSED     [ 50%]
inbox_api/tests/test_inbox_api.py::test_inbox_endpoints_crud PASSED      [100%]
2 passed, 1 warning in 8.17s
```

### npm run build (SUCCESS)
```
✓ Compiled successfully
✓ Linting and checking validity of types
✓ Generating static pages (21/21)
/inbox   5.79 kB   122 kB
✓ Build completed in 26.7s
```

## API Endpoints Verified
- GET /inbox → 200 (returns list, empty=ok)
- POST /inbox → 201 (creates inbox event)
- POST /inbox/{id}/read → 200 (marks as read)
- POST /inbox/bulk-archive → 200 (archives in bulk)
- GET /inbox/unread-count → 200 (returns count)

## Frontend Changes
- Removed all mock/placeholder/setTimeout from inbox-view.tsx
- Real fetch to GET /inbox via apiBase
- Real consume of unread-count, mark-read, bulk-archive
- Empty state rendered when API returns empty list (no simulated data)
