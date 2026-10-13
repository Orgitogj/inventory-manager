import pytest
from pydantic import ValidationError

from app.config import Settings


def test_new_settings_have_safe_defaults(monkeypatch):
    for name in (
        "CORS_ORIGINS",
        "LOGIN_MAX_ATTEMPTS",
        "LOGIN_WINDOW_MINUTES",
        "LOGIN_MAX_ATTEMPTS_PER_IP",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.cors_origins == []
    assert settings.login_max_attempts == 5
    assert settings.login_window_minutes == 15
    assert settings.login_max_attempts_per_ip == 30


def test_cors_origins_are_read_as_a_comma_separated_list(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS", " http://localhost:3000 ,https://shop.example.com,"
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://localhost:3000",
        "https://shop.example.com",
    ]


def test_empty_cors_origins_mean_no_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")

    assert Settings(_env_file=None).cors_origins == []


@pytest.mark.parametrize(
    "value", ["*", "http://localhost:3000,*", "https://*.example.com"]
)
def test_wildcard_cors_origin_is_rejected(monkeypatch, value):
    monkeypatch.setenv("CORS_ORIGINS", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_wildcard_cors_origin_is_rejected_when_passed_directly():
    with pytest.raises(ValidationError):
        Settings(cors_origins=["*"], _env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("login_max_attempts", 0),
        ("login_max_attempts", 101),
        ("login_window_minutes", 0),
        ("login_window_minutes", 24 * 60 + 1),
        ("login_max_attempts_per_ip", 0),
        ("login_max_attempts_per_ip", 10_001),
    ],
)
def test_login_limits_are_bounded(name, value):
    with pytest.raises(ValidationError):
        Settings(**{name: value}, _env_file=None)
