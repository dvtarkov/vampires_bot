from aiogram import types

from screens.defend_action import DistrictActionList
from .registry import option
from screens.main_menu import MainMenuScreen


@option("actions_menu_back")
async def actions_menu_back(cb: types.CallbackQuery):
    await MainMenuScreen().run(message=cb.message)
    await cb.answer()


@option("actions_menu_defend")
async def actions_menu_defend(cb: types.CallbackQuery):
    await DistrictActionList().run(message=cb.message)
    await cb.answer()
