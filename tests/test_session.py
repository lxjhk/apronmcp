import pytest
from apronmcp.session import SessionManager, LoginError
from apronmcp.config import Config


def test_is_logged_out_detects_login_page():
    sm = SessionManager(Config(user="u", password="p"))
    login_html = '<form><input name="UserID"><input name="Password" type="password"></form>'
    assert sm.looks_like_login_page(login_html) is True


def test_is_logged_out_false_for_app_page():
    sm = SessionManager(Config(user="u", password="p"))
    app_html = '<div id="schedule">Welcome alice</div>'
    assert sm.looks_like_login_page(app_html) is False
