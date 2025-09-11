# options/politician_list.py
import logging

from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .registry import option
from db.session import get_session
from db.models import User, Politician, Action, ActionStatus, ActionType
from screens.politician_list import PoliticianActionList
from screens.settings_action import SettingsActionScreen


@option("action_politician_menu_back")
async def action_politician_menu_back(cb: types.CallbackQuery, state: FSMContext):
    from screens.actions import ActionsScreen
    await ActionsScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("action_politician_menu_next")
async def action_politician_menu_next(cb: types.CallbackQuery, state: FSMContext, **kwargs):
    action_kind = kwargs.get("action")
    await PoliticianActionList().run(message=cb.message, actor=cb.from_user, state=state, move="next",
                                     action=action_kind)
    await cb.answer()


@option("action_politician_menu_prev")
async def action_politician_menu_prev(cb: types.CallbackQuery, state: FSMContext, **kwargs):
    action_kind = kwargs.get("action")
    await PoliticianActionList().run(message=cb.message, actor=cb.from_user, state=state, move="prev",
                                     action=action_kind)
    await cb.answer()


@option("action_politician_menu_pick")
async def action_politician_menu_pick(cb: types.CallbackQuery, state: FSMContext, **kwargs):
    action_kind = kwargs.get("action")  # обычно 'influence', но не обязательно
    data = await state.get_data()
    idx = int(data.get("politician_list_index", 0))

    async with get_session() as session:
        user = await User.get_by_tg_id(session, cb.from_user.id)

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
            await cb.answer("Нет доступных политиков.", show_alert=True)
            return

        # безопасно нормализуем индекс и берём выбранного политика
        idx = idx % len(rows)
        picked = rows[idx]

        logging.info(
            "Picked politician: id=%s name=%s (idx=%s of %s)",
            picked.id, picked.name, idx, len(rows)
        )

        # 1) Тип действия — строго INFLUENCE
        action_type = ActionType.INFLUENCE

        # 2) В action.district_id пишем район, привязанный к политику (может быть None)
        district_id = picked.district_id

        action = await Action.create(
            session,
            owner_id=user.id,
            status=ActionStatus.DRAFT,
            kind=action_kind or "influence",
            title=f"{(action_kind or 'influence')} {picked.name}",
            district_id=district_id,
            type=action_type,
            force=0,
            money=0,
            influence=0,
            information=0,
            is_positive=True
        )

    await SettingsActionScreen().run(
        message=cb.message,
        actor=cb.from_user,
        state=state,
        move="prev",
        action_id=action.id,
        action=action,
    )
    await cb.answer()
