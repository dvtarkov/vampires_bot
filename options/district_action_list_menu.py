from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.actions import ActionsScreen
from screens.defend_action import DistrictActionList, DefendActionScreen
from .registry import option
from db.session import get_session
from db.models import District, User, Action, ActionType


@option("action_district_menu_back")
async def action_district_menu_back(cb: types.CallbackQuery, state: FSMContext):
    await ActionsScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("action_district_menu_next")
async def action_district_menu_next(cb: types.CallbackQuery, state: FSMContext):
    await DistrictActionList().run(message=cb.message, actor=cb.from_user, state=state, move="next")
    await cb.answer()


@option("action_district_menu_prev")
async def action_district_menu_prev(cb: types.CallbackQuery, state: FSMContext):
    await DistrictActionList().run(message=cb.message, actor=cb.from_user, state=state, move="prev")
    await cb.answer()


@option("action_district_menu_pick")
async def action_district_menu_pick(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = int(data.get("district_list_index", 0))

    async with get_session() as session:
        user = await User.get_by_tg_id(session, cb.from_user.id)

        districts = await District.get_by_owner(session, user.id)
        district_id = districts[idx % len(districts)].id if districts else None

        action = await Action.create(
            session,
            owner_id=user.id,
            kind="defend",
            title="Defend district" if district_id else "Defend (no district)",
            district_id=district_id,
            type=ActionType.INDIVIDUAL,
            force=0,
            money=0,
            influence=0,
            information=0
        )

    print(f"[DEBUG] Created action {action.id} for district {district_id}")
    await DefendActionScreen().run(message=cb.message, actor=cb.from_user, state=state, move="prev",
                                   action_id=action.id, action=action)
    await cb.answer()
