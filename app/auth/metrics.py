"""Auth counters. auth_login_total is the basis of the sign-in SLI."""

from prometheus_client import Counter

LOGINS = Counter("auth_login", "Login attempts", ["result"])
REFRESHES = Counter("auth_refresh", "Refresh attempts", ["result"])

# Export both series at 0 from the start so SLI ratios are defined before the first failure.
for _counter in (LOGINS, REFRESHES):
    for _result in ("success", "failure"):
        _counter.labels(_result)
