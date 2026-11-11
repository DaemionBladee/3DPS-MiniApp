from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote_plus

from app.core.errors import AuthError


@dataclass(frozen=True, slots=True)
class VerifiedTelegramUser:
    telegram_id: int
    display_name: str
    username: str | None
    auth_date: datetime
    proof_hash: str


def _invalid() -> AuthError:
    return AuthError(401, "invalid_telegram_data", "Telegram authentication is invalid or expired.")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def verify_init_data(
    raw: str,
    bot_token: str,
    *,
    now: datetime | None = None,
    max_age_seconds: int = 300,
    future_skew_seconds: int = 30,
) -> VerifiedTelegramUser:
    """Official Telegram bot-token HMAC validation, not third-party Ed25519 mode.

    Remove only `hash` from sorted decoded key=value fields. The optional signed
    `signature` field participates in this bot-token HMAC data-check-string.
    """
    fields: dict[str, str] = {}
    try:
        if not raw or len(raw.encode("utf-8")) > 16_384 or len(raw.split("&")) > 64:
            raise ValueError
        for part in raw.split("&"):
            if "=" not in part or re.search(r"%(?![0-9a-fA-F]{2})", part):
                raise ValueError
            key_raw, value_raw = part.split("=", 1)
            key = unquote_plus(key_raw, encoding="utf-8", errors="strict")
            value = unquote_plus(value_raw, encoding="utf-8", errors="strict")
            if (
                not re.fullmatch(r"[A-Za-z0-9_]{1,64}", key)
                or key in fields
                or any(character in value for character in ("\x00", "\r", "\n"))
            ):
                raise ValueError
            fields[key] = value
        supplied_hash = fields.pop("hash")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_hash):
            raise ValueError
        auth_date_raw = fields["auth_date"]
        user_raw = fields["user"]
        if not re.fullmatch(r"[0-9]{1,12}", auth_date_raw):
            raise ValueError
        timestamp = int(auth_date_raw)
        reference = (now or datetime.now(UTC)).timestamp()
        if timestamp > reference + future_skew_seconds or timestamp < reference - max_age_seconds:
            raise ValueError
        data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
        secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        digest = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(digest, bytes.fromhex(supplied_hash)):
            raise ValueError
        user = json.loads(user_raw, object_pairs_hook=_unique_json_object)
        if not isinstance(user, dict):
            raise ValueError
        telegram_id = user.get("id")
        first_name = user.get("first_name")
        last_name = user.get("last_name", "")
        username = user.get("username")
        if (
            type(telegram_id) is not int
            or not 0 < telegram_id < 2**63
            or not isinstance(first_name, str)
            or not first_name.strip()
            or len(first_name) > 256
            or not isinstance(last_name, str)
            or len(last_name) > 256
            or (username is not None and (not isinstance(username, str) or len(username) > 64))
        ):
            raise ValueError
        for name in (first_name, last_name, username):
            if name is not None:
                name.encode("utf-8", errors="strict")
                if any(character in name for character in ("\x00", "\r", "\n")):
                    raise ValueError
        return VerifiedTelegramUser(
            telegram_id=telegram_id,
            display_name=f"{first_name} {last_name}".strip(),
            username=username,
            auth_date=datetime.fromtimestamp(timestamp, UTC),
            # Encoding/order variants of the same signed evidence share one key.
            proof_hash=hashlib.sha256(data_check_string.encode("utf-8") + digest).hexdigest(),
        )
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise _invalid() from None
