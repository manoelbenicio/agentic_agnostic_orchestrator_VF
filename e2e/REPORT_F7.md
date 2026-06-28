# AOP F7 E2E Report

- Profile: `full`
- Overall: `passed`
- API URL: `http://127.0.0.1:8090`
- Web URL: `http://127.0.0.1:13000`
- Generated UTC: `2026-06-27T22:27:55.053444+00:00`

## Checks

- `passed` G1 `f7.g1.health`: health ok
- `passed` G1 `f7.g1.ready`: ready
- `passed` G1 `f7.g1.metrics`: metrics include control-plane liveness
- `passed` G3 `f7.g3.ui_routes`: 12/12 routes passed
- `passed` G6 `f7.g6.perf_smoke`: p95 approx 8 ms over 6 samples
- `skipped` G7 `f7.g7.a11y_smoke`: Playwright/axe runner not installed in AOP/e2e yet
- `skipped` G4 `f7.g4.critical_journey`: Use test_contracts_wave1.py for current deep workflow coverage

## Evidence

- `F7_EVIDENCE.json`
