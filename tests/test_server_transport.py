import pytest

from apronmcp.server import transport_from_env


def test_default_is_stdio():
    assert transport_from_env(None) == "stdio"


def test_explicit_stdio():
    assert transport_from_env("stdio") == "stdio"


def test_http_maps_to_streamable_http():
    assert transport_from_env("http") == "streamable-http"


def test_unknown_value_raises():
    with pytest.raises(ValueError, match="APRONMCP_TRANSPORT"):
        transport_from_env("carrier-pigeon")
