# options/communicate.py
from aiogram import types
from aiogram.fsm.context import FSMContext

from options.registry import option
from screens.actions import ActionsScreen  # или ваш главный экран


@option("communicate_prompt_back")
async def communicate_prompt_back(cb: types.CallbackQuery, state: FSMContext):
    # Сбросим состояние ожидания текста и вернёмся на главный экран
    await state.clear()
    await ActionsScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()
