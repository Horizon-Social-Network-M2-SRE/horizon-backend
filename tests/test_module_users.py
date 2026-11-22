from app.users.router import router


def test_users_router_is_mounted(app):
    assert router.prefix == "/users"
    assert router in [r for r in app.state.module_routers]
