import pytest
from pydantic import ValidationError

from tests.conftest import make_settings
from tests.signing import BOT_TOKEN, SESSION_SECRET

TEST_DSN = "postgresql+asyncpg://test:test@127.0.0.1:5432/3dps_test_settings"


def test_defaults_keep_real_operations_and_mock_auth_disabled() -> None:
    settings = make_settings(TEST_DSN)
    assert settings.simulation_mode
    assert settings.cookie_name.startswith("__Host-")
    assert not settings.development_auth_enabled
    assert settings.session_ttl_seconds == 3600
    assert settings.auth_max_age_seconds == 300
    assert settings.auth_future_skew_seconds == 30


@pytest.mark.parametrize(
    "override",
    [
        {"development_auth_enabled": True},
        {"binding_quotes_enabled": True},
        {"auto_quote_enabled": True},
        {"payment_policy_approved": True},
        {"live_payments_enabled": True},
        {"real_printing_enabled": True},
        {"simulation_mode": False},
    ],
)
def test_production_cannot_enable_mock_auth_or_live_operations(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_settings(TEST_DSN, app_env="production", **override)


@pytest.mark.parametrize(
    "override",
    [
        {"database_url": "sqlite+aiosqlite:///:memory:"},
        {"public_base_url": "http://public.example", "app_env": "production"},
        {"public_base_url": "https://example.test/app"},
        {"public_base_url": "https://username:password@example.test"},
        {"session_secret": "short"},
        {"bot_token": ""},
        {"owner_telegram_ids": "-1"},
        {"owner_telegram_ids": "not-a-number"},
        {"session_ttl_seconds": 0},
        {"auth_max_age_seconds": 999999},
    ],
)
def test_unsafe_configuration_fails_closed(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_settings(TEST_DSN, **override)


def test_validation_error_does_not_print_configured_credentials() -> None:
    with pytest.raises(ValidationError) as failure:
        make_settings(TEST_DSN, app_env="production", development_auth_enabled=True)
    assert BOT_TOKEN not in str(failure.value)
    assert SESSION_SECRET not in str(failure.value)


def test_owner_allowlist_is_explicit_and_empty_means_no_owner() -> None:
    assert make_settings(TEST_DSN, owner_telegram_ids="").owner_ids == frozenset()
    assert make_settings(TEST_DSN, owner_telegram_ids="12, 34").owner_ids == frozenset({12, 34})
