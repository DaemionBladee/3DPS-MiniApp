import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode

import pytest
from aiogram.utils.web_app import check_webapp_signature

from app.core.errors import AuthError
from app.core.telegram import verify_init_data
from tests.signing import BOT_TOKEN, CUSTOMER_ID, fields_for, sign_fields

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


def example_fields() -> dict[str, str]:
    return fields_for(timestamp=int(NOW.timestamp()))


def rejects(raw: str) -> None:
    with pytest.raises(AuthError) as failure:
        verify_init_data(raw, BOT_TOKEN, now=NOW)
    assert failure.value.status == 401
    assert failure.value.code == "invalid_telegram_data"


def test_valid_raw_data_agrees_with_independent_aiogram_reference() -> None:
    fields = example_fields()
    fields["user"] = json.dumps({"id": CUSTOMER_ID, "first_name": "မြန်မာ", "last_name": "Test"})
    raw = sign_fields(fields)
    assert check_webapp_signature(BOT_TOKEN, raw)
    verified = verify_init_data(raw, BOT_TOKEN, now=NOW)
    assert verified.telegram_id == CUSTOMER_ID
    assert verified.display_name == "မြန်မာ Test"
    assert verified.auth_date.tzinfo is not None
    assert len(verified.proof_hash) == 64


def test_signature_field_is_included_for_bot_token_hmac_mode() -> None:
    fields = example_fields()
    fields["signature"] = "synthetic-optional-ed25519-field"
    raw = sign_fields(fields)
    assert check_webapp_signature(BOT_TOKEN, raw)
    assert verify_init_data(raw, BOT_TOKEN, now=NOW).telegram_id == CUSTOMER_ID
    rejects(raw.replace("synthetic-optional-ed25519-field", "tampered"))


def test_hmac_with_wrong_bot_token_is_rejected() -> None:
    rejects(sign_fields(example_fields(), bot_token="different:synthetic-bot-token"))


def test_url_encoding_and_order_do_not_change_replay_proof_identity() -> None:
    raw = sign_fields(example_fields())
    alternate = urlencode(list(reversed(parse_qsl(raw)))).replace("%7B", "%7b")
    first = verify_init_data(raw, BOT_TOKEN, now=NOW)
    second = verify_init_data(alternate, BOT_TOKEN, now=NOW)
    assert first.proof_hash == second.proof_hash


@pytest.mark.parametrize("field", ["hash", "auth_date", "user"])
def test_required_fields_cannot_be_missing(field: str) -> None:
    fields = example_fields()
    if field == "hash":
        raw = urlencode(fields)
    else:
        del fields[field]
        raw = sign_fields(fields)
    rejects(raw)


@pytest.mark.parametrize("field", ["hash", "auth_date", "user", "query_id", "%75ser"])
def test_duplicate_signed_fields_are_rejected_after_decoding(field: str) -> None:
    raw = sign_fields(example_fields())
    rejects(f"{raw}&{field}=duplicate")


@pytest.mark.parametrize("offset", [-301, 31, -10000, 3600])
def test_expired_or_future_authentication_is_rejected(offset: int) -> None:
    fields = example_fields()
    fields["auth_date"] = str(int((NOW + timedelta(seconds=offset)).timestamp()))
    rejects(sign_fields(fields))


@pytest.mark.parametrize("timestamp", ["", "1.5", "true", "-1", " 123", "9999999999999999999999"])
def test_malformed_timestamp_is_rejected(timestamp: str) -> None:
    fields = example_fields()
    fields["auth_date"] = timestamp
    rejects(sign_fields(fields))


@pytest.mark.parametrize(
    "user",
    [
        "not-json",
        "[]",
        "null",
        '{"id":1,"id":2,"first_name":"duplicate"}',
        '{"id":true,"first_name":"Boolean"}',
        '{"id":"1001","first_name":"String"}',
        '{"id":0,"first_name":"Zero"}',
        '{"id":-2,"first_name":"Negative"}',
        '{"id":9223372036854775808,"first_name":"Overflow"}',
        '{"first_name":"Missing id"}',
        '{"id":1001,"first_name":12}',
        '{"id":1001,"first_name":"   "}',
        '{"id":1001,"first_name":"Test","username":17}',
        '{"id":1001,"first_name":"Test","last_name":null}',
    ],
)
def test_malformed_user_cannot_create_verified_identity(user: str) -> None:
    fields = example_fields()
    fields["user"] = user
    rejects(sign_fields(fields))


@pytest.mark.parametrize("malformed", ["", "bad", "user=%GG", "user=%FF", "user=x&", "x=1\n2", "\ud800"])
def test_malformed_raw_encoding_fails_closed(malformed: str) -> None:
    rejects(malformed)


@pytest.mark.parametrize("hash_value", ["", "zz" * 32, "a" * 63, "a" * 65])
def test_hash_format_is_strict(hash_value: str) -> None:
    fields = example_fields()
    fields["hash"] = hash_value
    rejects(urlencode(fields))


def test_oversized_and_ambiguous_multiline_fields_are_rejected() -> None:
    fields = example_fields()
    fields["query_id"] = "x" * 17000
    rejects(sign_fields(fields))
    fields["query_id"] = "line-one\nline-two"
    rejects(sign_fields(fields))
