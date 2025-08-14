# screens/district_list.py
import logging
from typing import List
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, District
from .base import BaseScreen
from keyboards.presets import district_list_kb


class DistrictList(BaseScreen):
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        move: str | None = None,   # 'next' | 'prev' | None
        **kwargs
    ):
        tg_id = actor.id if actor else message.from_user.id
        logging.info("DistrictList for tg_id=%s", tg_id)

        async with get_session() as session:
            # пользователь нам всё ещё может понадобиться для будущих прав
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

            # ВСЕ районы, без фильтра owner_id
            rows: List[District] = (
                await session.execute(
                    select(District)
                    .options(selectinload(District.owner))       # если хочешь показывать владельца
                    .order_by(District.name, District.id)        # сортировка по имени/ид
                )
            ).scalars().all()

        if not rows:
            return {
                "district": None,
                "info": {"count": 0, "index": 0},
                "keyboard": district_list_kb(),
            }

        # индекс из FSM
        idx = 0
        if state:
            data = await state.get_data()
            idx = int(data.get("district_list_index", 0))

        # прокрутка
        if move == "next":
            idx = (idx + 1) % len(rows)
        elif move == "prev":
            idx = (idx - 1) % len(rows)

        # на всякий — clamp, если число районов изменилось
        if idx >= len(rows) or idx < 0:
            idx = 0

        if state:
            await state.update_data(district_list_index=idx)

        district = rows[idx]
        info = {"count": len(rows), "index": idx + 1}

        return {
            "district": district,
            "info": info,
            "keyboard": district_list_kb()
        }
