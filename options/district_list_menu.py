from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.district_list import DistrictList
from .registry import option


@option("district_list_menu_back")
async def district_list_menu_back(cb: types.CallbackQuery, state: FSMContext):
    from screens.main_menu import MainMenuScreen
    await MainMenuScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("district_list_menu_next")
async def district_list_menu_next(cb: types.CallbackQuery, state: FSMContext):
    await DistrictList().run(message=cb.message, actor=cb.from_user, state=state, move="next")
    await cb.answer()


@option("district_list_menu_prev")
async def district_list_menu_prev(cb: types.CallbackQuery, state: FSMContext):
    await DistrictList().run(message=cb.message, actor=cb.from_user, state=state, move="prev")
    await cb.answer()
