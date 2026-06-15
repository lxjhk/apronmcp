import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://advantage.paperlessfbo.com"


class ConfigError(Exception):
    """Raised when required configuration is missing."""


@dataclass
class Config:
    user: str
    password: str = field(repr=False)  # never show in repr/logs
    base_url: str = DEFAULT_BASE_URL


def load_config() -> Config:
    load_dotenv()  # load .env if present; real env vars take precedence
    user = os.environ.get("PAPERLESS_USER")
    password = os.environ.get("PAPERLESS_PASS")
    if not user or not password:
        raise ConfigError(
            "PAPERLESS_USER and PAPERLESS_PASS must be set (see .env.example)."
        )
    base_url = os.environ.get("PAPERLESS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    return Config(user=user, password=password, base_url=base_url)
