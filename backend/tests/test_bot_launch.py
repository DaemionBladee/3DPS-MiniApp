import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User
from telegram_bot.__main__ import ProviderLogFilter, launch_keyboard, launch_router

from tests.signing import BOT_TOKEN


def test_launch_keyboard_contains_only_configured_https_app_link() -> None:
    markup = launch_keyboard("https://miniapp.example/")
    button = markup.inline_keyboard[0][0]
    assert button.text == "Open 3DPS"
    assert button.web_app is not None
    assert button.web_app.url == "https://miniapp.example/app"
    assert button.callback_data is None
    assert BOT_TOKEN not in markup.model_dump_json()


@pytest.mark.parametrize(
    "origin",
    [
        "http://miniapp.example",
        "javascript:alert(1)",
        "https://username:password@miniapp.example",
        "https://miniapp.example/private-path",
        "https://miniapp.example?token=secret",
        "https://miniapp.example#fragment",
    ],
)
def test_launch_rejects_unsafe_or_credential_bearing_origins(origin: str) -> None:
    with pytest.raises(ValueError):
        launch_keyboard(origin)


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type,expected_replies", [("private", 1), ("group", 0)])
async def test_start_launch_button_is_private_chat_only(chat_type: str, expected_replies: int) -> None:
    session = AsyncMock()
    bot = Bot(BOT_TOKEN, session=session)
    dispatcher = Dispatcher()
    dispatcher.include_router(launch_router("https://miniapp.example"))
    update = Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=1001, type=chat_type),
            from_user=User(id=1001, first_name="Synthetic", is_bot=False),
            text="/start",
        ),
    )
    await dispatcher.feed_update(bot, update)
    assert session.await_count == expected_replies
    if expected_replies:
        method = session.call_args.args[1]
        assert method.chat_id == 1001
        assert method.reply_markup.inline_keyboard[0][0].web_app.url == "https://miniapp.example/app"


def test_provider_error_log_filter_drops_urls_arguments_and_tracebacks() -> None:
    marker = "DO_NOT_LOG_PROVIDER_SECRET"
    record = logging.LogRecord("aiohttp.client", logging.ERROR, "synthetic", 1, marker, (marker,), None)
    record.exc_text = marker
    assert ProviderLogFilter().filter(record)
    assert marker not in record.getMessage()
    assert record.getMessage() == "telegram_provider_error"
    assert record.args == () and record.exc_info is None and record.exc_text is None


def test_application_event_logs_keep_sanitized_event_codes() -> None:
    record = logging.LogRecord("3dps.telegram", logging.ERROR, "synthetic", 1, "telegram_launch_failed", (), None)
    assert ProviderLogFilter().filter(record)
    assert record.getMessage() == "telegram_launch_failed"
