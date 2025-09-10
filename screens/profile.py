import logging
from aiogram import types
from sqlalchemy import select, func
from db.session import get_session
from db.models import User, District, Action, ActionStatus, ActionType
from keyboards.spec import KeyboardParams, KeyboardSpec
from .base import BaseScreen


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
                user = await User.create(
                    session=session,
                    tg_id=tg_id,
                    username=(actor or message.from_user).username,
                    first_name=(actor or message.from_user).first_name,
                    last_name=(actor or message.from_user).last_name,
                    language_code=(actor or message.from_user).language_code,
                )

            # --- Районы ---
            districts = await District.get_by_owner(session, user.id)
            districts_count = len(districts)
            districts_view = [f"{d.name} — ОК: {d.control_points}" for d in districts]

            # --- Разведка: список из M2M и "сейчас скаутится" по pending-экшену ---
            scouts = list(user.scouts_districts)  # lazy="selectin" подтянет внутри сессии
            scouts_view = [f"{d.name}" for d in scouts]

            current_scout_stmt = (
                select(Action)
                .where(
                    Action.owner_id == user.id,
                    Action.status == ActionStatus.PENDING,
                    Action.type.in_([ActionType.SCOUT_DISTRICT, ActionType.SCOUT_INFO]),
                    Action.district_id.is_not(None),
                )
                .order_by(Action.created_at.desc())
                .limit(1)
            )
            current_scout_action = (await session.execute(current_scout_stmt)).scalars().first()
            current_scout_name = current_scout_action.district.name if current_scout_action and current_scout_action.district else None

            # --- Статистика действий ---
            stats_stmt = (
                select(Action.status, func.count())
                .where(
                    Action.owner_id == user.id,
                    Action.status.in_([ActionStatus.PENDING, ActionStatus.DONE, ActionStatus.FAILED]),
                )
                .group_by(Action.status)
            )
            stats_rows = (await session.execute(stats_stmt)).all()
            stats_map = {status: int(cnt) for status, cnt in stats_rows}
            pending_count = stats_map.get(ActionStatus.PENDING, 0)
            done_count = stats_map.get(ActionStatus.DONE, 0)
            failed_count = stats_map.get(ActionStatus.FAILED, 0)

            # --- Последние действия ---
            recent_stmt = (
                select(Action)
                .where(Action.owner_id == user.id)
                .order_by(Action.created_at.desc())
                .limit(5)
            )
            recent_actions = [
                f"({a.status.value})" for a in (await session.execute(recent_stmt)).scalars().all()
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
                "list": districts_view,
            },
            "scouting": {
                "active_count": len(scouts),
                "has_any": len(scouts) > 0,
                "list": scouts_view,
                "current": current_scout_name,  # None или название района
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
            "keyboard": KeyboardSpec(
                type="inline",
                name="profile_menu",
                options=["back"],
                params=KeyboardParams(max_in_row=2),
            ),
        }