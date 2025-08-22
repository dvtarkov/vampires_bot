# screens/news_list.py
import logging
from math import ceil
from typing import List
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import timezone

from db.session import get_session
from db.models import News
from .base import BaseScreen
from keyboards.presets import news_list_kb  # см. ниже

# Сколько новостей показывать на одной странице
PAGE_SIZE = 3  # <--- меняешь это число, и размер страницы меняется


def human(dt):
    try:
        return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC") if dt else "—"
    except Exception:
        return "—"


class NewsList(BaseScreen):
    async def _pre_render(
            self,
            message: types.Message,
            actor: types.User | None = None,
            state: FSMContext | None = None,
            move: str | None = None,  # 'next' | 'prev' | None
            **kwargs
    ):
        logging.info("NewsList for tg_id=%s", (actor or message.from_user).id)

        # --- читаем текущую страницу из FSM ---
        page = 0
        if state:
            data = await state.get_data()
            page = int(data.get("news_page_index", 0))

        # Если это «первый вход» без move — сбрасываем на первую страницу
        if move is None:
            page = 0
        elif move == "next":
            page += 1
        elif move == "prev":
            page -= 1

        # --- считаем всего новостей и страниц ---
        async with get_session() as session:
            total_count = (
                              await session.execute(select(func.count(News.id)))
                          ).scalar() or 0

            if total_count == 0:
                # Пусто — отдаём заглушку
                if state:
                    await state.update_data(news_page_index=0)
                return {
                    "news_page": {
                        "items": [],
                        "page": 0,
                        "pages": 0,
                        "total": 0,
                    },
                    "keyboard": news_list_kb(disabled=True),
                }

            pages = max(1, ceil(total_count / PAGE_SIZE))

            # Нормализуем страницу (кольцевая пагинация)
            if page < 0:
                page = pages - 1
            if page >= pages:
                page = 0

            # Запрашиваем конкретную порцию новостей
            stmt = (
                select(News)
                .options(selectinload(News.action))
                .order_by(News.created_at.desc())
                .limit(PAGE_SIZE)
                .offset(page * PAGE_SIZE)
            )
            rows: List[News] = (await session.execute(stmt)).scalars().all()

        # Сериализуем в компактный вид для шаблона
        items = []
        for n in rows:
            items.append({
                "id": n.id,
                "title": n.title,
                "body": n.body,  # если нужно — сократить в шаблоне/здесь
                "created_human": human(n.created_at),
                "updated_human": human(n.updated_at),
                "media_count": len(n.media_urls or []),
                "media_urls": n.media_urls or [],
                "action": {
                    "id": n.action.id,
                    "title": n.action.title,
                    "kind": n.action.kind,
                } if n.action else None,
            })

        # Сохраняем текущую страницу в FSM
        if state:
            await state.update_data(news_page_index=page)

        return {
            "news_page": {
                "items": items,
                "page": page + 1,  # человекочитаемая (1..pages)
                "pages": pages,
                "total": total_count,
                "page_size": PAGE_SIZE,
            },
            "keyboard": news_list_kb(disabled=False),
        }
