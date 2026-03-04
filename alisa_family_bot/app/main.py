from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.config import get_settings
from app.db import engine
from app.handlers import admin, channel, engagement, start
from app.models import Base
from app.services.scheduler import scheduler_worker

logging.basicConfig(level=logging.INFO)

settings = get_settings()
scheduler_task: asyncio.Task | None = None


async def on_startup(bot: Bot) -> None:
    global scheduler_task

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустити бота"),
        ]
    )

    if settings.webhook_url:
        await bot.set_webhook(settings.webhook_url, secret_token=settings.webhook_secret)

    scheduler_task = asyncio.create_task(scheduler_worker(bot))


async def on_shutdown(bot: Bot) -> None:
    global scheduler_task

    if settings.webhook_url:
        await bot.delete_webhook(drop_pending_updates=False)

    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        scheduler_task = None


async def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(channel.router)
    dp.include_router(engagement.router)
    return dp


async def run_polling() -> None:
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = await create_dispatcher()
    await on_startup(bot)
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown(bot)
        await bot.session.close()


async def run_webhook() -> None:
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = await create_dispatcher()

    dp.startup.register(lambda *_: on_startup(bot))
    dp.shutdown.register(lambda *_: on_shutdown(bot))

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)

    async def healthcheck(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", healthcheck)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.host, port=settings.port)
    await site.start()
    logging.info("Webhook server started on %s:%s", settings.host, settings.port)

    stop_event = asyncio.Event()
    await stop_event.wait()


def main() -> None:
    if settings.webhook_url:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
