# horizon-backend

Horizon social network backend API (Python 3.12+, FastAPI, Pydantic v2, MongoDB, Redis).

## Layout

```
app/
  main.py          create_app(): lifespan (MongoDB + Redis), routers, metrics
  modules.py       registry of feature module routers
  core/            config, db (AsyncMongoClient), redis, health, metrics
  auth/ users/ connections/ posts/ feed/ interactions/   one package per module, router under /<module>
tests/             one test per module, health, metrics
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload
```

| Endpoint        | Purpose                                                   |
|-----------------|-----------------------------------------------------------|
| `/health`       | liveness, no dependencies                                 |
| `/health/ready` | readiness: pings MongoDB and Redis, `503` if one is down  |
| `/metrics`      | Prometheus metrics                                        |
| `/docs`         | OpenAPI UI                                                |

Configuration (environment or `.env`): `JWT_SECRET` (**required**), `MONGODB_URI` (default `mongodb://localhost:27017`),
`MONGODB_DB` (`horizon`), `REDIS_URL` (`redis://localhost:6379/0`).

## Tests

Tests needing MongoDB or Redis are skipped when they are unreachable. To run everything:

```bash
docker run -d --rm --name horizon-mongo-test -p 127.0.0.1:27018:27017 mongo:7
docker run -d --rm --name horizon-redis-test -p 127.0.0.1:6380:6379 redis:7
TEST_MONGODB_URI=mongodb://localhost:27018 TEST_REDIS_URL=redis://localhost:6380/15 .venv/bin/pytest
```

## Container

```bash
docker build -t horizon-backend .
docker run -p 8000:8000 -e JWT_SECRET=... -e MONGODB_URI=... -e REDIS_URL=... horizon-backend
```

Multi-stage image, runs as uid 10001. CI builds it and checks `/health` answers.

## Auth

| Endpoint             | Request                                | Result                                                       |
|----------------------|----------------------------------------|--------------------------------------------------------------|
| `POST /auth/login`   | form `username` (email), `password`    | `{access_token, token_type, expires_in}` (JWT, 15 min) + refresh cookie |
| `POST /auth/refresh` | refresh cookie (sent by the browser)   | new access token + new cookie; the old refresh token stops working |
| `POST /auth/logout`  | bearer token                           | `204`, cookie cleared, session ended, access token refused until it expires |
| `GET /auth/me`       | bearer token                           | `{"id": ...}`                                                |

- **`JWT_SECRET` is required** (32+ characters); the app refuses to start without it. Never commit it:
  set it in `.env` locally, in Compose, and in the Kubernetes Secret.
  Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- The refresh token is only ever in a cookie: `refresh_token`, `HttpOnly; Secure; SameSite=Strict; Path=/api/auth`.
  The web client calls with `credentials: 'include'`. When calling the API directly (no Traefik `/api` prefix),
  set `REFRESH_COOKIE_PATH=/auth`; over plain http locally, `REFRESH_COOKIE_SECURE=false`.
- Each login is a session (`sid` claim). Redis keys:
  `auth:session:<sid>` -> current refresh hash, `auth:refresh:<sha256>` -> `<user>:<sid>` (7-day TTL),
  `auth:deny:<jti>` (TTL = remaining access token lifetime).
- Users are read from the `users` collection: lowercase `email`, argon2 `passwordHash`
  (`app/auth/security.py`, shared with register).
- Metrics: `auth_login_total{result="success|failure"}`, `auth_refresh_total{result=...}`.
- Protect a route with `claims: CurrentUser` from `app.auth.deps`.
