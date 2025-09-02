# services/notify.py
from typing import Optional
from aiogram import Bot
from screens.notify_screen import NotifyScreen
import logging


async def notify_user(
    bot: Bot,
    user_tg_id: int,
    *,
    title: str,
    body: str,
    parse_mode: Optional[str] = "HTML",
    persist_key: str | None = None,
):
    """
    Отправляет пользователю push‑уведомление (в его личку с ботом).
    Требует: BaseScreen._render умеет работать с chat_id и bot.
    """
    try:
        screen = NotifyScreen()
        await screen.run(
            message=None,            # можно без исходного message
            bot=bot,                 # <- обязательно передаём bot
            chat_id=user_tg_id,      # <- явный чат для доставки
            title=title,
            body=body,
            parse_mode=parse_mode,
            render_kind="notice",    # на всякий случай дублируем
            force_new=True,
            persist_key=persist_key or f"notify:{user_tg_id}",
            disable_web_page_preview=True,
        )
    except Exception as ex:
        logging.error(f"Error during notify: {ex}")
