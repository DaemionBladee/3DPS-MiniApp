from __future__ import annotations

import asyncio
import logging
import sys
from urllib.parse import urlsplit

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from app.core.config import Settings

logger = logging.getLogger("3dps.telegram")


class ProviderLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(("aiogram", "aiohttp")):
            record.msg = "telegram_provider_error"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


def launch_keyboard(origin: str) -> InlineKeyboardMarkup:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Telegram launch requires the configured HTTPS Mini App origin")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open 3DPS", web_app=WebAppInfo(url=f"{origin.rstrip('/')}/app"))]
        ]
    )


def launch_router(origin: str) -> Router:
    keyboard = launch_keyboard(origin)
    router = Router(name="miniapp_launch")

    @router.message(CommandStart(), F.chat.type == "private")
    async def start(message: Message) -> None:
        await message.answer("Your private print and design workspace.", reply_markup=keyboard)

    @router.errors()
    async def launch_error(_event: ErrorEvent) -> bool:
        # Never log provider exception URLs, which can contain the bot token.
        logger.error("telegram_launch_failed")
        return True

    return router


async def run() -> None:
    settings = Settings()
    keyboard = launch_keyboard(settings.origin)
    web_app = keyboard.inline_keyboard[0][0].web_app
    assert web_app is not None
    dispatcher = Dispatcher()
    dispatcher.include_router(launch_router(settings.origin))
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        await bot.set_my_commands(
            [BotCommand(command="start", description="Open your 3DPS workspace")],
            scope=BotCommandScopeAllPrivateChats(),
        )
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Open 3DPS", web_app=web_app))
        await dispatcher.start_polling(bot, allowed_updates=["message"], close_bot_session=False)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    # Third-party HTTP/update errors may contain provider URLs. Emit only our
    # event codes; never log raw updates, signed initData or configuration.
    for handler in logging.getLogger().handlers:
        handler.addFilter(ProviderLogFilter())
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        return
    except Exception:
        print("telegram_startup_failed: verify secure test bot and HTTPS configuration.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
