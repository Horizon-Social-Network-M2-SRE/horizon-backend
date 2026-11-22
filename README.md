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

Configuration (environment or `.env`): `MONGODB_URI` (default `mongodb://localhost:27017`),
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
docker run -p 8000:8000 -e MONGODB_URI=... -e REDIS_URL=... horizon-backend
```

Multi-stage image, runs as uid 10001. CI builds it and checks `/health` answers.
