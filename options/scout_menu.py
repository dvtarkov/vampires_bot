# options/scout.py
import logging
from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.scout_action import ScoutActionScreen
from screens.scout_info_screen import ScoutInfoScreen
from screens.settings_action import DistrictActionList
from .registry import option

# from screens.scout_menu_info_question import ScoutInfoQuestionScreen  # если нужен ввод вопроса
# или можно пока просто ответить callback'ом


@option("scout_menu_scout_district")
async def scout_menu_district(cb: types.CallbackQuery, state: FSMContext, action: str = "scout", **_):
    logging.info("Scout district chosen by user_id=%s, payload action=%s", cb.from_user.id, action)
    # Пример перехода в выбор района под действие scout:
    try:
        await DistrictActionList().run(message=cb.message, actor=cb.from_user, state=state, move=None, action="scout")
    except Exception:
        # если такого экрана нет/ещё не готов — просто уведомим
        await cb.answer("Вы выбрали: разведка района.", show_alert=True)
    else:
        await cb.answer()


@option("scout_menu_scout_info")
async def scout_menu_info(cb: types.CallbackQuery, state: FSMContext, action: str = "scout", **_):
    logging.info("Scout info chosen by user_id=%s, payload action=%s", cb.from_user.id, action)
    await ScoutInfoScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("scout_menu_back")
async def scout_menu_choice_menu_back(cb: types.CallbackQuery, state: FSMContext):
    # Верни пользователя туда, откуда пришёл (например, ActionsScreen/MainMenuScreen)
    from screens.actions import ActionsScreen
    await ActionsScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer("Возврат назад.", show_alert=False)


@option("scout_info_back")
async def scout_info_back(cb: types.CallbackQuery, state: FSMContext, **_):
    """
    Сбросить ожидание текста и вернуть к экрану выбора режима разведки.
    """
    try:
        if state:
            await state.clear()
        await ScoutActionScreen().run(message=cb.message, actor=cb.from_user, state=state)
        await cb.answer()
    except Exception as e:
        logging.exception("scout_info_back failed")
        await cb.answer(f"Ошибка: {e}", show_alert=True)
