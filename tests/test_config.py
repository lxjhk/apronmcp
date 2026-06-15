import pytest
from paperless141_mcp.config import load_config, ConfigError


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


def test_repr_does_not_leak_password(monkeypatch):
    monkeypatch.setenv("PAPERLESS_USER", "alice")
    monkeypatch.setenv("PAPERLESS_PASS", "secret")
    cfg = load_config()
    assert "secret" not in repr(cfg)
