# screens/notify.py
import logging
from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.base import BaseScreen


class NotifyScreen(BaseScreen):
    """
    Простой экран уведомления: заголовок + текст.
    Шлёт как notice (всегда новое сообщение).
    """
    async def _pre_render(
        self,
        message: types.Message | None = None,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        *,
        title: str,
        body: str,
        **kwargs
    ):
        # ничего особенного — просто отдаём контекст в шаблон
        ctx = {
            "title": title.strip() if title else "Уведомление",
            "body": body.strip() if body else "",
        }

        # render_kind="notice" => всегда новое сообщение
        # force_new=True        => не пытаемся редактировать старые
        return {
            "bot": kwargs.get("bot"),
            "chat_id": kwargs.get("chat_id"),
            "notify": ctx,
            "render_kind": "notice",
            "force_new": True,
            # persist_key можно оставить общим либо параметризовать вызовом
            "persist_key": kwargs.get("persist_key", "notice"),
            # можно передать parse_mode через kwargs при вызове
        }
