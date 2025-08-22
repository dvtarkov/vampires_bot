# options/news_list.py
from aiogram import types
from aiogram.fsm.context import FSMContext

from options.registry import option
from screens.main_menu import MainMenuScreen
from screens.news_list import NewsList


@option("news_list_menu_prev")
async def news_prev(cb: types.CallbackQuery, state: FSMContext, **_):
    await NewsList().run(message=cb.message, actor=cb.from_user, state=state, move="prev")
    await cb.answer()


@option("news_list_menu_next")
async def news_next(cb: types.CallbackQuery, state: FSMContext, **_):
    await NewsList().run(message=cb.message, actor=cb.from_user, state=state, move="next")
    await cb.answer()


@option("news_list_menu_back")
async def news_back(cb: types.CallbackQuery, state: FSMContext, **_):
    # вернись на нужный экран (главное меню, например)

    await MainMenuScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()
