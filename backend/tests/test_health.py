def test_health_reports_db(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_request_id_header(client):
    r = client.get("/api/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/api/chat", headers={"Origin": "http://localhost:3000",
                                              "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options("/api/chat", headers={"Origin": "https://evil.example",
                                               "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_database_url_normalisation():
    from app.config import normalise_database_url

    assert normalise_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_database_url("sqlite:///./dev.db") == "sqlite:///./dev.db"


def test_cors_origins_strip_trailing_slash():
    from app.config import Settings

    s = Settings(CORS_ORIGINS="https://a.vercel.app/, http://localhost:3000")
    assert s.cors_origins == ["https://a.vercel.app", "http://localhost:3000"]
