"""Host and cross-origin protections for the local control panel."""


def test_untrusted_host_header_is_rejected(client) -> None:
    """DNS-rebinding requests with a foreign Host header cannot reach the app."""
    response = client.get("/api/status", headers={"Host": "evil.example"})

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "Host" in response.json()["error"]


def test_cross_origin_mutation_is_rejected(client) -> None:
    """A browser mutation from another origin is blocked before routing."""
    response = client.post(
        "/api/routing/apply",
        headers={"Origin": "https://evil.example"},
        json={"method": "static"},
    )

    assert response.status_code == 403
    assert "Cross-origin" in response.json()["error"]


def test_same_origin_mutation_is_not_rejected_by_the_guard(client) -> None:
    """The normal same-origin browser path still reaches the application."""
    response = client.post(
        "/api/routing/apply",
        headers={"Origin": "http://testserver"},
        json={"method": "static"},
    )

    assert response.status_code == 404
