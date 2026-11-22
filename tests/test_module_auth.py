from app.auth.router import router


def test_auth_router_is_mounted(app):
    assert router.prefix == "/auth"
    assert router in [r for r in app.state.module_routers]
