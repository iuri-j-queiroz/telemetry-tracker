"""Tests for the F1TV live gate. No network access."""

import datetime as dt

import jwt
import pytest
from fastf1.internals import f1auth

from server import live


@pytest.fixture
def auth_file(tmp_path, monkeypatch):
    path = tmp_path / "f1auth.json"
    monkeypatch.setattr(f1auth, "AUTH_DATA_FILE", path)
    return path


def make_token(expires_in_s: float = 86_400, product: str = "F1 TV Pro") -> str:
    claims = {
        "exp": dt.datetime.now(dt.UTC).timestamp() + expires_in_s,
        "SubscribedProduct": product,
        "SubscriptionStatus": "Subscribed",
    }
    return jwt.encode(claims, key="test-secret-0123456789abcdef-0123456789", algorithm="HS256")


def test_missing_credentials(auth_file):
    status = live.credential_status()
    assert status["has_credentials"] is False
    assert status["state"] == "missing"


def test_valid_credentials(auth_file):
    auth_file.write_text(make_token(), encoding="utf-8")
    status = live.credential_status()
    assert status["has_credentials"] is True
    assert status["state"] == "valid"
    assert status["product"] == "F1 TV Pro"
    assert status["expires"]


def test_expired_credentials(auth_file):
    auth_file.write_text(make_token(expires_in_s=-60), encoding="utf-8")
    status = live.credential_status()
    assert status["has_credentials"] is False
    assert status["state"] == "expired"


def test_invalid_token(auth_file):
    auth_file.write_text("this is not a jwt", encoding="utf-8")
    status = live.credential_status()
    assert status["has_credentials"] is False
    assert status["state"] == "invalid"


def test_auth_session_start_and_cancel():
    info = live.AUTH.start()
    assert info["state"] == "waiting"
    assert "f1login.fastf1.dev?port=" in info["url"]
    info = live.AUTH.cancel()
    assert info["state"] == "idle"


def test_capture_requires_credentials(auth_file):
    with pytest.raises(live.LiveError):
        live.CAPTURE.start({"year": 2026, "round": 17, "code": "R"})


def test_live_status_shape(auth_file, monkeypatch):
    monkeypatch.setattr(live.catalog, "live_window", lambda now=None: None)
    status = live.live_status()
    assert status["has_credentials"] is False
    assert status["capture"]["state"] == "idle"
    assert status["live_window"] is None
    assert status["reason"]
