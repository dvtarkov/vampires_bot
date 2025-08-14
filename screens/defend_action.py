# screens/district_list.py
import logging
from datetime import timezone
from typing import List
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, District, ActionStatus, ActionType, Action
from .base import BaseScreen
from keyboards.presets import district_list_kb, action_district_list_kb, action_setup_kb


class DistrictActionList(BaseScreen):
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
            "keyboard": action_district_list_kb("defend")
        }


class DefendActionScreen(BaseScreen):
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        move: str | None = None,   # 'next' | 'prev' | None
        **kwargs
    ):
        tg_id = actor.id if actor else message.from_user.id
        logging.info("DefendActionScreen for tg_id=%s", tg_id)

        def human(dt):
            try:
                return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC") if dt else "—"
            except Exception:
                return "—"

        # -------- 1) достаём пользователя --------
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

            # -------- 2) достаём/получаем действие --------
            action_obj: Action | None = kwargs.get("action")
            action_id: int | None = kwargs.get("action_id")

            if not action_obj and action_id:
                action_obj = (await session.execute(
                    select(Action).where(Action.id == action_id)
                )).scalars().first()

            # -------- 3) формируем контекст для шаблона --------
            if action_obj:
                # district может быть None
                district_name = action_obj.district.name if action_obj.district else None
                owner_name = (
                    action_obj.owner.first_name
                    or action_obj.owner.username
                    or str(user.tg_id)
                )

                support = {
                    "is_support": action_obj.parent_action_id is not None,
                    "parent_id": action_obj.parent_action_id,
                    "parent_title": action_obj.parent_action.title if action_obj.parent_action else None,
                    "children_count": len(action_obj.support_actions) if action_obj.support_actions is not None else 0,
                }

                action_ctx = {
                    "id": action_obj.id,
                    "kind": action_obj.kind,
                    "title": action_obj.title,
                    "status": action_obj.status.value if isinstance(action_obj.status, ActionStatus) else (action_obj.status or "pending"),
                    "type": action_obj.type.value if isinstance(action_obj.type, ActionType) else (action_obj.type or "individual"),
                    "owner": {"name": owner_name},
                    "district": {"name": district_name} if district_name else None,
                    "created_human": human(action_obj.created_at),
                    "updated_human": human(action_obj.updated_at),
                    "resources": {
                        "force": action_obj.force,
                        "money": action_obj.money,
                        "influence": action_obj.influence,
                        "information": action_obj.information,
                    },
                    "support": support,
                }
            else:
                # дефолтный «черновик» defend без района
                action_ctx = {
                    "id": None,
                    "kind": "defend",
                    "title": kwargs.get("title"),
                    "status": ActionStatus.PENDING.value,
                    "type": ActionType.INDIVIDUAL.value,
                    "owner": {
                        "name": user.first_name or user.username or str(user.tg_id)
                    },
                    "district": None,  # не выбран
                    "created_human": "—",
                    "updated_human": "—",
                    "resources": {
                        "force": kwargs.get("force", 0),
                        "money": kwargs.get("money", 0),
                        "influence": kwargs.get("influence", 0),
                        "information": kwargs.get("information", 0),
                    },
                    "support": {
                        "is_support": False,
                        "parent_id": None,
                        "parent_title": None,
                        "children_count": 0,
                    },
                }

        # -------- 4) вернуть контекст + клавиатуру --------
        # Если хочешь менять состав кнопок — передай список ресурсов здесь
        logging.info("Jinja ctx keys for %s: %s",
                      self.__class__.__name__, action_ctx)

        return {
            "action": action_ctx,
            "keyboard": action_setup_kb(["force", "money", "influence", "information"])
        }
