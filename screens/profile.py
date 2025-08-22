import logging
from aiogram import types
from sqlalchemy import select, func
from db.session import get_session
from db.models import User, District
from .base import BaseScreen
from keyboards.presets import main_menu_kb


def ideology_bar(value: int, size: int = 11) -> str:
    """Рисуем шкалу ▪/⬛️ по -size..+size. Здесь просто 0..size c зелёной точкой."""
    filled = max(0, min(size, value + 5))
    return "▪" * filled + "💠" + "▪" * (size - filled - 1)


class ProfileScreen(BaseScreen):
    async def _pre_render(self, message: types.Message, actor: types.User | None = None, **kwargs):
        tg_id = actor.id if actor else (message.from_user.id if message else None)
        logging.info("StatusScreen for tg_id=%s", tg_id)

        async with get_session() as session:
            user = await User.get_by_tg_id(session, tg_id)
            if user is None:
                # на всякий: создадим, чтобы экран всегда работал
                user = await User.create(
                    session=session,
                    tg_id=tg_id,
                    username=(actor or message.from_user).username,
                    first_name=(actor or message.from_user).first_name,
                    last_name=(actor or message.from_user).last_name,
                    language_code=(actor or message.from_user).language_code,
                )

            districts_count = await session.scalar(
                select(func.count(District.id)).where(District.owner_id == user.id)
            ) or 0

        # --- Статистика действий ---
        pending_count = sum(1 for a in user.actions if a.status == "pending")
        done_count = sum(1 for a in user.actions if a.status == "done")
        failed_count = sum(1 for a in user.actions if a.status == "failed")

        # --- Последние действия (по created_at, максимум 5) ---
        recent_actions = [
            f"({a.status})"
            for a in sorted(user.actions, key=lambda x: x.created_at, reverse=True)[:5]
        ]

        profile = {
            "name": user.in_game_name or user.username or str(user.tg_id),
            "faction": user.faction,
            "ideology_value": user.ideology,
            "ideology_label": user.ideology,
            "ideology_bar": ideology_bar(user.ideology, size=11),
            "resources": {
                "force": user.force,
                "money": user.money,
                "influence": user.influence,
                "information": user.information,
            },
            "applications": {
                "available": user.available_actions,
                "max_available": user.max_available_actions,
                "next_update_minutes": user.actions_refresh_at,
                "fast_actions": kwargs.get("fast_actions_left", 3),
            },
            "districts": {
                "count": districts_count,
                "has_any": districts_count > 0,
            },
            "actions_stats": {
                "pending": pending_count,
                "done": done_count,
                "failed": failed_count,
            },
            "recent_actions": recent_actions,
        }

        return {
            "profile": profile,
            "keyboard": main_menu_kb(),
        }
