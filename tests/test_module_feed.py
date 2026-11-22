from app.feed.router import router


def test_feed_router_is_mounted(app):
    assert router.prefix == "/feed"
    assert router in [r for r in app.state.module_routers]
