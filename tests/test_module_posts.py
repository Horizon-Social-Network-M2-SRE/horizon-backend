from app.posts.router import router


def test_posts_router_is_mounted(app):
    assert router.prefix == "/posts"
    assert router in [r for r in app.state.module_routers]
