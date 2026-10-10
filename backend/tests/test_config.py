from app.config import Settings


def test_llm_defaults_target_groq():
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "groq"
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.llm_model == "openai/gpt-oss-120b"


def test_llm_configuration_can_be_overridden_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-a-real-credential")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "groq"
    assert settings.llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.llm_model == "openai/gpt-oss-120b"
    assert settings.llm_api_key == "test-key-not-a-real-credential"


def test_cors_origins_accept_vercel_production_origin():
    settings = Settings(
        _env_file=None,
        app_cors_origins="http://localhost:5173,https://incident-iq-tau.vercel.app",
    )

    assert settings.cors_origins == [
        "http://localhost:5173",
        "https://incident-iq-tau.vercel.app",
    ]
