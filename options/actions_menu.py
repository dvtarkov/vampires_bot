from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.communicate_screen import CommunicateScreen
from screens.scout_action import ScoutActionScreen
from screens.settings_action import DistrictActionList
from .registry import option
from screens.main_menu import MainMenuScreen


@option("actions_menu_back")
async def actions_menu_back(cb: types.CallbackQuery):
    await MainMenuScreen().run(message=cb.message)
    await cb.answer()


@option("actions_menu_defend")
async def actions_menu_defend(cb: types.CallbackQuery):
    await DistrictActionList().run(message=cb.message, action="defend")
    await cb.answer()


@option("actions_menu_attack")
async def actions_menu_attack(cb: types.CallbackQuery):
    await DistrictActionList().run(message=cb.message, action="attack")
    await cb.answer()


@option("actions_menu_scout")
async def actions_menu_scout(cb: types.CallbackQuery):
    await ScoutActionScreen().run(message=cb.message, action="scout")
    await cb.answer()


@option("actions_menu_communicate")
async def actions_menu_communicate(cb: types.CallbackQuery, state: FSMContext):
    await CommunicateScreen().run(message=cb.message, action="scout", state=state)
    await cb.answer()
