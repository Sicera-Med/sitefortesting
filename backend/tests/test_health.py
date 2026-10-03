def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"


def test_root_health_probe(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version(client):
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "triage-backend"
    assert body["api_prefix"] == "/api/v1"
