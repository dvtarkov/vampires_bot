# screens/notify.py
import logging
from aiogram import types
from aiogram.fsm.context import FSMContext

from keyboards.presets import winlose_kb
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


class AskWhoWonScreen(BaseScreen):
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
        action_id: int,
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
            "force_new": True,
            "keyboard": winlose_kb(str(action_id)),
        }


class AdminWhoWonScreen(BaseScreen):
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
        who_applied: dict,
        **kwargs
    ):
        # ничего особенного — просто отдаём контекст в шаблон
        ctx = {
            "title": title.strip() if title else "Уведомление",
            "who_applied": who_applied,
        }

        # render_kind="notice" => всегда новое сообщение
        # force_new=True        => не пытаемся редактировать старые
        return {
            "bot": kwargs.get("bot"),
            "chat_id": kwargs.get("chat_id"),
            "notify": ctx,
            "render_kind": "notice",
            "force_new": True,
            "persist_key": kwargs.get("persist_key", "notice"),
            "keyboard": winlose_kb(kwargs.get("action_id")),
        }
