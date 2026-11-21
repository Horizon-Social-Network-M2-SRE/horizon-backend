# horizon-backend

Horizon social network backend API (Python 3.12+, FastAPI, Pydantic v2).

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/uvicorn app.main:app --reload   # GET /health
```

## Profiles

`app/models/profile.py` defines the user profile, discriminated by `userType`:

| userType | required type-specific field |
|----------|------------------------------|
| student  | `major`                      |
| staff    | `adminRole`                  |
| teacher  | `speciality`                 |

Fields belonging to another user type are rejected. Use `parse_profile(payload)` to validate.
