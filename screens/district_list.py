# screens/district_list.py
import logging
from typing import List
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, District, Politician
from .base import BaseScreen
from keyboards.presets import district_list_kb


def ideology_bar(value: int, size: int = 11) -> str:
    """Рисуем шкалу ▪/💠 по -5..+5 (value). Центр — 💠."""
    # value ∈ [-5..+5] -> позиция [0..10]
    pos = max(-5, min(5, int(value))) + 5
    left = "▪" * pos
    right = "▪" * (size - pos - 1)
    return f"{left}💠{right}"


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

            rows: List[District] = (
                await session.execute(
                    select(District)
                    .options(selectinload(District.owner))
                    .order_by(District.name.asc(), District.id.asc())
                )
            ).scalars().all()

        if not rows:
            return {
                "district": None,
                "info": {"count": 0, "index": 0},
                "politicians": [],
                "keyboard": district_list_kb(),
            }

        # ===== Индекс =====
        if state:
            data = await state.get_data()
        else:
            data = {}

        # Если на экран пришли без move — считаем это «первым входом» и сбрасываем индекс.
        if move is None:
            idx = 0
        else:
            idx = int(data.get("district_list_index", 0))
            if move == "next":
                idx = (idx + 1) % len(rows)
            elif move == "prev":
                idx = (idx - 1) % len(rows)

        # Защита от выхода за границы
        if idx >= len(rows) or idx < 0:
            idx = 0

        if state:
            await state.update_data(district_list_index=idx)

        district = rows[idx]
        info = {"count": len(rows), "index": idx + 1}

        # ===== 2) Политики по району =====
        # Подтягиваем список политиков для выбранного района.
        async with get_session() as session:
            pols = await Politician.by_district(session, district.id)

        politicians = [
            {
                "id": p.id,
                "name": p.name,
                "role_and_influence": p.role_and_influence,
                "ideology": p.ideology,
                "ideology_bar": ideology_bar(p.ideology),
                "influence": p.influence,
                "bonuses_penalties": p.bonuses_penalties or "",
            }
            for p in pols
        ]

        return {
            "district": district,
            "info": info,
            "politicians": politicians,   # <-- отдаём в шаблон
            "keyboard": district_list_kb(),
        }
