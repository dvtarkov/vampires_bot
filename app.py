import asyncio
import logging
from aiogram import Bot, Dispatcher
from logging_config import setup_logging
from config import load_config
from middlewares.timing import TimingMW
from routes import router as main_router
from routes.options import router as options_router
from options.registry import load_all_options
from middlewares.user_registration import UserRegistrationMiddleware
from text_handlers import load_all_text_handlers, _REGISTRY


config = load_config()
setup_logging(level=config.log_level)


async def main():
    logging.info("Starting bot…")
    # 1) грузим все опции, чтобы сработали декораторы @option
    load_all_options()
    load_all_text_handlers("text_handlers")  # <-- ВАЖНО: до start_polling
    logging.info("Text handlers at start: %s", list(_REGISTRY.keys()))

    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    dp.update.middleware(TimingMW())
    dp.message.middleware(UserRegistrationMiddleware())
    dp.callback_query.middleware(UserRegistrationMiddleware())

    # сначала основной роутинг (команды/экраны и т.п.)
    dp.include_router(main_router)
    # затем универсальный обработчик опций
    dp.include_router(options_router)

    try:
        await dp.start_polling(bot)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logging.info("Shutdown requested, stopping polling…")
    except Exception:
        logging.exception("Fatal error in polling")
        raise
    finally:
        logging.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
