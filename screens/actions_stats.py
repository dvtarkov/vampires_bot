# screens/actions_stats.py
import logging
from typing import Dict

from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, Action, ActionStatus
from screens.base import BaseScreen
from keyboards.presets_actions_stats import actions_stats_kb


class ActionsStatsScreen(BaseScreen):
    """
    Показывает счётчики действий пользователя по статусам.
    Кнопки: Draft / Pending / Success / Fail / Back
    """
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        **kwargs
    ):
        tg_id = (actor or message.from_user).id
        logging.info("ActionsStatsScreen for tg_id=%s", tg_id)

        async with get_session() as session:
            user = await User.get_by_tg_id(session, tg_id)
            if not user:
                user = await User.create(
                    session=session,
                    tg_id=tg_id,
                    username=(actor or message.from_user).username,
                    first_name=(actor or message.from_user).first_name,
                    last_name=(actor or message.from_user).last_name,
                    language_code=(actor or message.from_user).language_code,
                )

            # сгруппированные суммы по статусам
            rows = (
                await session.execute(
                    select(Action.status, func.count(Action.id))
                    .where(Action.owner_id == user.id)
                    .group_by(Action.status)
                )
            ).all()


        # нормализуем к нулям
        counts: Dict[str, int] = {"draft": 0, "pending": 0, "success": 0, "fail": 0}
        for st, cnt in rows:
            if st == ActionStatus.DRAFT:
                counts["draft"] = int(cnt)
            elif st == ActionStatus.PENDING:
                counts["pending"] = int(cnt)
            elif st == ActionStatus.DONE:
                counts["success"] = int(cnt)
            elif st == ActionStatus.FAILED:
                counts["fail"] = int(cnt)

        return {
            "stats": counts,
            "keyboard": actions_stats_kb(counts),
        }
