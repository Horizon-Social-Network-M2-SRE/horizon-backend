def test_metrics_endpoint_exposes_prometheus_format(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "python_info" in response.text


def test_requests_are_counted_by_route_template(client):
    client.get("/users/does-not-exist")
    text = client.get("/metrics").text
    assert 'route="unmatched"' in text
    assert "/users/does-not-exist" not in text  # raw paths never become labels
