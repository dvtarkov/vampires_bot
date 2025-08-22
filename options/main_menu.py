from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.actions import ActionsScreen
from screens.district_list import DistrictList
from screens.news_list import NewsList
from screens.profile import ProfileScreen
from .registry import option
from screens.main_menu import MainMenuScreen


@option("main_menu_actions")
async def main_menu_actions(cb: types.CallbackQuery):
    await ActionsScreen().run(message=cb.message)
    await cb.answer()


@option("main_menu_map")  # или своя опция
async def open_districts(cb: types.CallbackQuery, state: FSMContext, **_):
    # сбросим индекс на 0 при первом заходе (необязательно)
    await state.update_data(district_list_index=0)
    await DistrictList().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("main_menu_news")
async def main_menu_news(cb: types.CallbackQuery, state: FSMContext, **_):
    await NewsList().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("main_menu_profile")
async def main_menu_profile(cb: types.CallbackQuery):
    await ProfileScreen().run(message=cb.message, actor=cb.from_user)
    await cb.answer()


@option("main_menu_help")
async def main_menu_help(cb: types.CallbackQuery):
    await MainMenuScreen().run(message=cb.message)
    await cb.answer()
