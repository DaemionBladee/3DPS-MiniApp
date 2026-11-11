from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Fail-closed server settings; never loaded from browser-provided fields."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "staging", "production"] = "development"
    database_url: SecretStr
    bot_token: SecretStr
    session_secret: SecretStr
    public_base_url: str
    owner_telegram_ids: str = ""
    session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    auth_max_age_seconds: int = Field(default=300, ge=30, le=600)
    auth_future_skew_seconds: int = Field(default=30, ge=0, le=30)
    auth_rate_limit: int = Field(default=10, ge=1, le=100)
    auth_rate_window_seconds: int = Field(default=60, ge=1, le=3600)
    binding_quotes_enabled: bool = False
    auto_quote_enabled: bool = False
    payment_policy_approved: bool = False
    live_payments_enabled: bool = False
    real_printing_enabled: bool = False
    simulation_mode: bool = True
    development_auth_enabled: bool = False

    @property
    def owner_ids(self) -> frozenset[int]:
        if not self.owner_telegram_ids.strip():
            return frozenset()
        return frozenset(int(part.strip()) for part in self.owner_telegram_ids.split(","))

    @property
    def cookie_name(self) -> str:
        return "__Host-3dps_session"

    @property
    def origin(self) -> str:
        return self.public_base_url

    @model_validator(mode="after")
    def validate_security_configuration(self) -> Self:
        # Avoid including actual configuration values in these exception messages.
        if not self.database_url.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use PostgreSQL with asyncpg")
        if not self.bot_token.get_secret_value().strip():
            raise ValueError("BOT_TOKEN must be securely configured")
        if len(self.session_secret.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        parsed = urlsplit(self.public_base_url)
        try:
            _ = parsed.port
        except ValueError:
            raise ValueError("PUBLIC_BASE_URL must use a valid origin port") from None
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("PUBLIC_BASE_URL must be a single origin without credentials")
        if parsed.scheme != "https":
            if not (
                self.app_env in {"development", "test"}
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("PUBLIC_BASE_URL requires HTTPS outside local development")
        try:
            ids = self.owner_ids
            if any(value <= 0 or value >= 2**63 for value in ids):
                raise ValueError
        except ValueError:
            raise ValueError("OWNER_TELEGRAM_IDS must contain positive Telegram IDs") from None
        self.public_base_url = self.public_base_url.rstrip("/")
        if (
            self.binding_quotes_enabled
            or self.auto_quote_enabled
            or self.payment_policy_approved
            or self.live_payments_enabled
            or self.real_printing_enabled
            or not self.simulation_mode
            or self.development_auth_enabled
        ):
            raise ValueError("M02 permits secure authentication only; live and mock-auth gates must stay disabled")
        return self
