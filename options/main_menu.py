from aiogram import types

from screens.actions import ActionsScreen
from screens.profile import ProfileScreen
from .registry import option
from screens.main_menu import MainMenuScreen


@option("main_menu_actions")
async def main_menu_actions(cb: types.CallbackQuery):
    await ActionsScreen().run(message=cb.message)
    await cb.answer()


@option("main_menu_map")
async def main_menu_map(cb: types.CallbackQuery):
    await cb.answer("Карта сейчас недоступна 🗺️")


@option("main_menu_news")
async def main_menu_news(cb: types.CallbackQuery):
    await cb.answer("Новостей пока нет 🗞️")


@option("main_menu_profile")
async def main_menu_profile(cb: types.CallbackQuery):
    await ProfileScreen().run(message=cb.message, actor=cb.from_user)
    await cb.answer()


@option("main_menu_help")
async def main_menu_help(cb: types.CallbackQuery):
    await MainMenuScreen().run(message=cb.message)
    await cb.answer()
