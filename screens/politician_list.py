# screens/politician_list.py
import logging
from datetime import timezone
from typing import List, Optional

from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, Politician, Action, ActionStatus, ActionType
from keyboards.spec import KeyboardSpec, KeyboardParams
from .base import BaseScreen
from keyboards.presets import action_politician_list_kb  # см. ниже


def ideology_bar(value: int, size: int = 11) -> str:
    pos = max(-5, min(5, int(value))) + 5
    left = "▪" * pos
    right = "▪" * (size - pos - 1)
    return f"{left}💠{right}"


class PoliticianActionList(BaseScreen):
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        move: str | None = None,   # 'next' | 'prev' | None
        **kwargs
    ):
        action = kwargs.get("action")  # ожидаем 'scout' (но не критично)

        tg_id = actor.id if actor else message.from_user.id
        logging.info("PoliticianList for tg_id=%s", tg_id)

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

            rows = (
                await session.execute(
                    select(Politician)
                    .options(selectinload(Politician.district))
                    .order_by(
                        Politician.district_id.is_(None),  # non-null сначала, NULL — в конец
                        Politician.district_id.asc(),
                        Politician.name.asc(),
                    )
                )
            ).scalars().all()

        if not rows:
            return {
                "politician": None,
                "info": {"count": 0, "index": 0},
                "keyboard": KeyboardSpec(
                    type="inline",
                    name="politician_list_menu",
                    options=[["back"]],
                    params=KeyboardParams(max_in_row=1),
                    button_params={"back": {}},
                ),
            }

        if state:
            data = await state.get_data()
            idx = int(data.get("politician_list_index", 0))
        else:
            idx = 0

        if move == "next":
            idx = (idx + 1) % len(rows)
        elif move == "prev":
            idx = (idx - 1) % len(rows)

        if idx >= len(rows) or idx < 0:
            idx = 0

        if state:
            await state.update_data(politician_list_index=idx)

        pol = rows[idx]
        info = {"count": len(rows), "index": idx + 1}

        politician = {
            "id": pol.id,
            "name": pol.name,
            "role_and_influence": pol.role_and_influence,
            "ideology": pol.ideology,
            "ideology_bar": ideology_bar(pol.ideology),
            "influence": pol.influence,
            "bonuses_penalties": pol.bonuses_penalties or "",
            "district": pol.district.name if pol.district else None,
        }

        return {
            "politician": politician,
            "info": info,
            "keyboard": action_politician_list_kb(action),
        }
