# options/actions_stats.py
from aiogram import types
from aiogram.fsm.context import FSMContext

from options.registry import option


@option("actions_stats_menu_back")
async def actions_stats_menu_back(cb: types.CallbackQuery, state: FSMContext, **_):
    # вернуться к вашему экрану списка действий
    from screens.actions import ActionsScreen
    await ActionsScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("actions_stats_menu_draft")
async def actions_stats_menu_draft(cb: types.CallbackQuery, state: FSMContext, **_):
    # вернуться к вашему экрану списка действий
    from screens.settings_action import SettingsActionScreen
    await SettingsActionScreen().run(message=cb.message, actor=cb.from_user, state=state, is_list=True,
                                     statuses=["draft"])

    await cb.answer()


@option("actions_stats_menu_pending")
async def actions_stats_menu_pending(cb: types.CallbackQuery, state: FSMContext, **_):
    # вернуться к вашему экрану списка действий
    from screens.settings_action import SettingsActionScreen
    await SettingsActionScreen().run(message=cb.message, actor=cb.from_user, state=state, is_list=True,
                                     statuses=["pending"])

    await cb.answer()


@option("actions_stats_menu_success")
async def actions_stats_menu_success(cb: types.CallbackQuery, state: FSMContext, **_):
    # вернуться к вашему экрану списка действий
    from screens.settings_action import SettingsActionScreen
    await SettingsActionScreen().run(message=cb.message, actor=cb.from_user, state=state, is_list=True,
                                     statuses=["success"])

    await cb.answer()


@option("actions_stats_menu_fail")
async def actions_stats_menu_fail(cb: types.CallbackQuery, state: FSMContext, **_):
    # вернуться к вашему экрану списка действий
    from screens.settings_action import SettingsActionScreen
    await SettingsActionScreen().run(message=cb.message, actor=cb.from_user, state=state, is_list=True,
                                     statuses=["fail"])

    await cb.answer()
