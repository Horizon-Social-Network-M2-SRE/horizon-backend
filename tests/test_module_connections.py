from app.connections.router import router


def test_connections_router_is_mounted(app):
    assert router.prefix == "/connections"
    assert router in [r for r in app.state.module_routers]
