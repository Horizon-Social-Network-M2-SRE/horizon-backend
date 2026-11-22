from app.interactions.router import router


def test_interactions_router_is_mounted(app):
    assert router.prefix == "/interactions"
    assert router in [r for r in app.state.module_routers]
