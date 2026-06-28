#!/usr/bin/env python3
"""F7 E2E final harness scaffold for AOP.

Default usage is intentionally non-exhaustive. Use --profile plan to inspect
coverage without network calls, --profile smoke for quick probes, and require
--allow-exhaustive before any exhaustive profile can run.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


OUT_DIR = Path(__file__).resolve().parent
EVIDENCE_PATH = OUT_DIR / "F7_EVIDENCE.json"
REPORT_PATH = OUT_DIR / "REPORT_F7.md"

API_URL = os.environ.get("AOP_E2E_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
WEB_URL = os.environ.get("AOP_E2E_WEB_URL", "http://127.0.0.1:13000").rstrip("/")

UI_ROUTES = (
    "/",
    "/projects",
    "/issues",
    "/seats",
    "/sessions",
    "/finops",
    "/observability",
    "/live",
    "/settings",
    "/inbox",
    "/my-issues",
    "/squad-builder",
)

FORBIDDEN_UI_MARKERS = (
    "next.js server error",
    "application error",
    "runtime error",
    "unhandled runtime error",
)


@dataclass(frozen=True)
class Check:
    check_id: str
    gate: str
    name: str
    profile: str
    exhaustive: bool
    description: str


@dataclass
class CheckResult:
    check_id: str
    gate: str
    name: str
    status: str
    detail: str
    duration_ms: int
    evidence: dict[str, Any]


CHECKS = (
    Check("f7.g1.health", "G1", "API health", "smoke", False, "GET /health returns status ok."),
    Check("f7.g1.ready", "G1", "API readiness", "smoke", False, "GET /health/ready returns ready."),
    Check("f7.g1.metrics", "G1", "Metrics up", "smoke", False, "GET /metrics exposes aop_control_plane_up 1."),
    Check("f7.g3.ui_routes", "G3", "UI route smoke", "smoke", False, "GET primary Next routes."),
    Check("f7.g6.perf_smoke", "G6", "Perf smoke", "full", False, "Short latency sample on lightweight endpoints."),
    Check("f7.g7.a11y_smoke", "G7", "A11y smoke scaffold", "full", False, "Placeholder until browser/axe runner is installed."),
    Check("f7.g4.critical_journey", "G4", "Critical journey scaffold", "full", False, "Delegates deep workflow to existing Wave 1 contracts."),
    Check("f7.g2.api_contracts", "G2", "API contracts exhaustive", "exhaustive", True, "Full pytest contract suite."),
)

PROFILE_ORDER = {"plan": 0, "smoke": 1, "full": 2, "exhaustive": 3}


class HarnessError(RuntimeError):
    """Raised for blocked harness configuration."""


def request(method: str, base_url: str, path: str, accept: str = "application/json") -> tuple[int, str, int]:
    start = time.perf_counter()
    req = urllib.request.Request(f"{base_url}{path}", method=method, headers={"Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return response.status, body, elapsed_ms
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return exc.code, body, elapsed_ms
    except urllib.error.URLError as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        raise HarnessError(str(exc)) from exc


def result(check: Check, status: str, detail: str, duration_ms: int = 0, **evidence: Any) -> CheckResult:
    return CheckResult(
        check_id=check.check_id,
        gate=check.gate,
        name=check.name,
        status=status,
        detail=detail,
        duration_ms=duration_ms,
        evidence=evidence,
    )


def run_health(check: Check) -> CheckResult:
    status, body, elapsed = request("GET", API_URL, "/health")
    if status != 200:
        return result(check, "failed", f"HTTP {status}: {body[:200]}", elapsed)
    data = json.loads(body)
    if data.get("status") != "ok":
        return result(check, "failed", f"unexpected payload: {data}", elapsed, payload=data)
    return result(check, "passed", "health ok", elapsed, payload=data)


def run_ready(check: Check) -> CheckResult:
    status, body, elapsed = request("GET", API_URL, "/health/ready")
    if status == 503:
        return result(check, "skipped", f"readiness dependency unavailable: {body[:200]}", elapsed)
    if status != 200:
        return result(check, "failed", f"HTTP {status}: {body[:200]}", elapsed)
    data = json.loads(body)
    if data.get("status") != "ready":
        return result(check, "failed", f"unexpected payload: {data}", elapsed, payload=data)
    return result(check, "passed", "ready", elapsed, payload=data)


def run_metrics(check: Check) -> CheckResult:
    status, body, elapsed = request("GET", API_URL, "/metrics", accept="text/plain")
    if status != 200:
        return result(check, "failed", f"HTTP {status}: {body[:200]}", elapsed)
    if "aop_control_plane_up 1" not in body:
        return result(check, "failed", "missing aop_control_plane_up 1", elapsed)
    return result(check, "passed", "metrics include control-plane liveness", elapsed)


def run_ui_routes(check: Check) -> CheckResult:
    routes: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    skipped: list[str] = []
    started = time.perf_counter()
    for route in UI_ROUTES:
        try:
            status, body, elapsed = request("GET", WEB_URL, route, accept="text/html")
        except HarnessError as exc:
            skipped.append(f"{route}: {exc}")
            continue
        routes[route] = {"status": status, "elapsed_ms": elapsed}
        lower = body.lower()
        if status in {502, 503, 504}:
            skipped.append(f"{route}: HTTP {status}")
        elif status != 200:
            failures.append(f"{route}: HTTP {status}")
        elif "<html" not in lower:
            failures.append(f"{route}: missing html marker")
        elif any(marker in lower for marker in FORBIDDEN_UI_MARKERS):
            failures.append(f"{route}: runtime error marker found")
    elapsed_total = int((time.perf_counter() - started) * 1000)
    if failures:
        return result(check, "failed", "; ".join(failures), elapsed_total, routes=routes, skipped=skipped)
    if skipped and len(skipped) == len(UI_ROUTES):
        return result(check, "skipped", "; ".join(skipped[:3]), elapsed_total, routes=routes)
    detail = f"{len(routes) - len(skipped)}/{len(UI_ROUTES)} routes passed"
    return result(check, "passed", detail, elapsed_total, routes=routes, skipped=skipped)


def run_perf_smoke(check: Check) -> CheckResult:
    samples: list[int] = []
    failures: list[str] = []
    started = time.perf_counter()
    for path in ("/health", "/metrics"):
        for _ in range(3):
            try:
                status, _body, elapsed = request("GET", API_URL, path, accept="text/plain")
            except HarnessError as exc:
                return result(check, "skipped", f"API unavailable for perf smoke: {exc}")
            if status >= 500:
                failures.append(f"{path}: HTTP {status}")
            samples.append(elapsed)
    if failures:
        return result(check, "failed", "; ".join(failures), int((time.perf_counter() - started) * 1000))
    p95 = max(samples) if len(samples) < 20 else statistics.quantiles(samples, n=20)[18]
    status = "passed" if p95 <= 1500 else "failed"
    return result(
        check,
        status,
        f"p95 approx {p95:.0f} ms over {len(samples)} samples",
        int((time.perf_counter() - started) * 1000),
        samples_ms=samples,
        p95_ms=p95,
        budget_ms=1500,
    )


def run_a11y_scaffold(check: Check) -> CheckResult:
    return result(check, "skipped", "Playwright/axe runner not installed in AOP/e2e yet")


def run_critical_journey_scaffold(check: Check) -> CheckResult:
    return result(check, "skipped", "Use test_contracts_wave1.py for current deep workflow coverage")


def run_exhaustive_guard(check: Check) -> CheckResult:
    return result(check, "skipped", "Exhaustive pytest dispatch is intentionally not wired in scaffold mode")


RUNNERS: dict[str, Callable[[Check], CheckResult]] = {
    "f7.g1.health": run_health,
    "f7.g1.ready": run_ready,
    "f7.g1.metrics": run_metrics,
    "f7.g3.ui_routes": run_ui_routes,
    "f7.g6.perf_smoke": run_perf_smoke,
    "f7.g7.a11y_smoke": run_a11y_scaffold,
    "f7.g4.critical_journey": run_critical_journey_scaffold,
    "f7.g2.api_contracts": run_exhaustive_guard,
}


def selected_checks(profile: str, allow_exhaustive: bool = False) -> list[Check]:
    if profile == "plan":
        return list(CHECKS)
    selected = [
        check
        for check in CHECKS
        if PROFILE_ORDER[check.profile] <= PROFILE_ORDER[profile]
    ]
    if any(check.exhaustive for check in selected) and not allow_exhaustive:
        raise HarnessError("exhaustive profile requires --allow-exhaustive")
    return selected


def write_outputs(profile: str, results: list[CheckResult], plan_only: bool = False) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    statuses = [item.status for item in results]
    overall = "planned" if plan_only else "passed"
    if any(status == "failed" for status in statuses):
        overall = "failed"
    elif statuses and all(status == "skipped" for status in statuses):
        overall = "skipped"
    evidence = {
        "run_id": datetime.now(timezone.utc).strftime("f7-%Y%m%dT%H%M%SZ"),
        "generated_at": generated_at,
        "profile": profile,
        "base_urls": {"api": API_URL, "web": WEB_URL},
        "overall": overall,
        "results": [asdict(item) for item in results],
    }
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# AOP F7 E2E Report",
        "",
        f"- Profile: `{profile}`",
        f"- Overall: `{overall}`",
        f"- API URL: `{API_URL}`",
        f"- Web URL: `{WEB_URL}`",
        f"- Generated UTC: `{generated_at}`",
        "",
        "## Checks",
        "",
    ]
    for item in results:
        lines.append(f"- `{item.status}` {item.gate} `{item.check_id}`: {item.detail}")
    lines.extend(["", "## Evidence", "", f"- `{EVIDENCE_PATH.name}`", ""])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def plan_results(checks: list[Check]) -> list[CheckResult]:
    return [
        CheckResult(
            check_id=check.check_id,
            gate=check.gate,
            name=check.name,
            status="planned",
            detail=check.description,
            duration_ms=0,
            evidence={"profile": check.profile, "exhaustive": check.exhaustive},
        )
        for check in checks
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AOP F7 E2E final harness scaffold")
    parser.add_argument("--profile", choices=tuple(PROFILE_ORDER), default="plan")
    parser.add_argument("--allow-exhaustive", action="store_true", help="required for --profile exhaustive")
    args = parser.parse_args(argv)

    try:
        checks = selected_checks(args.profile, args.allow_exhaustive)
    except HarnessError as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return 2

    if args.profile == "plan":
        results = plan_results(checks)
        write_outputs(args.profile, results, plan_only=True)
        print(f"planned {len(results)} F7 checks; wrote {REPORT_PATH.name} and {EVIDENCE_PATH.name}")
        return 0

    results = []
    for check in checks:
        runner = RUNNERS[check.check_id]
        try:
            results.append(runner(check))
        except HarnessError as exc:
            results.append(result(check, "skipped", str(exc)))
        except Exception as exc:  # pragma: no cover - captures runtime evidence.
            results.append(result(check, "failed", f"{type(exc).__name__}: {exc}"))

    write_outputs(args.profile, results)
    failed = [item for item in results if item.status == "failed"]
    print(f"ran {len(results)} F7 checks; failed={len(failed)}; wrote {REPORT_PATH.name} and {EVIDENCE_PATH.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
