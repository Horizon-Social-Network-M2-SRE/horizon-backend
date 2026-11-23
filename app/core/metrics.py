"""Prometheus /metrics endpoint.

Exposes the default process and Python metrics plus a request counter and
latency histogram. S2-09 may replace this with prometheus-fastapi-instrumentator.
"""

import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)

_SKIP = {"/metrics", "/health", "/health/ready"}


def setup_metrics(app: FastAPI) -> None:
    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.middleware("http")
    async def _record(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        # An unhandled exception becomes a 500 for the client: count it as one, or the
        # error-rate SLI would read 0% during an outage.
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", None) or "unmatched"  # template, not raw path: bounded labels
            if path not in _SKIP:
                REQUESTS.labels(request.method, path, str(status_code)).inc()
                LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
