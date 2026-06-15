import pytest
from paperless141_mcp.config import load_config, ConfigError


@pytest.fixture(autouse=True)
def isolate_from_dotenv(monkeypatch):
    """Unit tests exercise env-var logic only — never let a real .env file (which
    exists for local runs) leak credentials into these tests. No-op load_dotenv."""
    monkeypatch.setattr("paperless141_mcp.config.load_dotenv", lambda *a, **k: None)


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("PAPERLESS_USER", "alice")
    monkeypatch.setenv("PAPERLESS_PASS", "secret")
    monkeypatch.delenv("PAPERLESS_BASE_URL", raising=False)
    cfg = load_config()
    assert cfg.user == "alice"
    assert cfg.password == "secret"
    assert cfg.base_url == "https://advantage.paperlessfbo.com"


def test_load_config_missing_creds_raises(monkeypatch):
    monkeypatch.delenv("PAPERLESS_USER", raising=False)
    monkeypatch.delenv("PAPERLESS_PASS", raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_missing_only_password_names_password(monkeypatch):
    monkeypatch.setenv("PAPERLESS_USER", "alice")
    monkeypatch.delenv("PAPERLESS_PASS", raising=False)
    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "PAPERLESS_PASS" in str(exc.value)
    assert "PAPERLESS_USER" not in str(exc.value)


def test_missing_only_user_names_user(monkeypatch):
    monkeypatch.delenv("PAPERLESS_USER", raising=False)
    monkeypatch.setenv("PAPERLESS_PASS", "secret")
    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "PAPERLESS_USER" in str(exc.value)
    assert "PAPERLESS_PASS" not in str(exc.value)


def test_repr_does_not_leak_password(monkeypatch):
    monkeypatch.setenv("PAPERLESS_USER", "alice")
    monkeypatch.setenv("PAPERLESS_PASS", "secret")
    cfg = load_config()
    assert "secret" not in repr(cfg)
