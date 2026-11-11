"""Independent Telegram test signer; never shared with browser/runtime code."""

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from urllib.parse import urlencode
from uuid import uuid4

BOT_TOKEN = "123456789:synthetic-test-token-never-contact-telegram"
SESSION_SECRET = "synthetic-m02-session-secret-never-use-outside-tests-12345"
ORIGIN = "https://testserver"
OWNER_ID = 9001
CUSTOMER_ID = 1001


def fields_for(
    user_id: int = CUSTOMER_ID,
    *,
    timestamp: int | None = None,
) -> dict[str, str]:
    return {
        "auth_date": str(int(time.time()) if timestamp is None else timestamp),
        "query_id": uuid4().hex,
        "user": json.dumps(
            {"id": user_id, "first_name": "Synthetic", "username": "test_customer"},
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    }


def sign_fields(fields: Mapping[str, str], *, bot_token: str = BOT_TOKEN) -> str:
    """Bot-token HMAC: only hash is excluded; signature remains a signed field."""
    unsigned = {key: value for key, value in fields.items() if key != "hash"}
    data_check = "\n".join(f"{key}={unsigned[key]}" for key in sorted(unsigned))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**unsigned, "hash": digest})


def signed_data(user_id: int = CUSTOMER_ID, *, timestamp: int | None = None) -> str:
    return sign_fields(fields_for(user_id, timestamp=timestamp))
