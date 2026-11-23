import importlib

import pytest
from fastapi import FastAPI

from app.main import create_app

MODULES = ["auth", "users", "connections", "posts", "feed", "interactions"]


@pytest.mark.parametrize("module", MODULES)
def test_module_router_is_mounted_by_the_app(module, settings, monkeypatch):
    router = importlib.import_module(f"app.{module}.router").router
    assert router.prefix == f"/{module}"

    mounted = []
    real_include = FastAPI.include_router

    def spy(self, r, *args, **kwargs):
        mounted.append(r)
        return real_include(self, r, *args, **kwargs)

    monkeypatch.setattr(FastAPI, "include_router", spy)
    create_app(settings)
    assert any(r is router for r in mounted)  # identity: empty routers compare equal with ==
