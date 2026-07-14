from app.config import Settings


def test_cors_origins_accept_comma_separated_environment_value(monkeypatch) -> None:
    monkeypatch.setenv("APP_CORS_ORIGINS", "http://localhost:5173,http://localhost:4173")

    settings = Settings()

    assert settings.app_cors_origins == [
        "http://localhost:5173",
        "http://localhost:4173",
    ]
