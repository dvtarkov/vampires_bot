# screens/scout_info_screen.py
import logging
from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.base import BaseScreen
from states.scout import Scout
from keyboards.presets import scout_info_kb


class ScoutInfoScreen(BaseScreen):
    """
    Просит ввести текст вопроса для мастеров.
    Предупреждает, что вопрос будет стоить 1🧠 information.
    Ставит FSM в ожидание текста: Scout.waiting_question
    """
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        error_text: str | None = None,
        **kwargs
    ):
        user = actor or message.from_user
        logging.info("ScoutInfoScreen for tg_id=%s", user.id)

        if state:
            await state.set_state(Scout.waiting_question)

        ctx = {
            "title": "🕵️ Разведка: вопрос мастерам",
            "lines": [
                "Введите ваш вопрос для мастерской группы в одном сообщении.",
                "Стоимость: 1 🧠 information.",
                "После создания заявку нельзя отменить или удалить.",
            ],
            "hint": "Напишите ваш вопрос (от 1 до 600 символов):",
            "error_text": error_text,   # опционально покажем ошибку
        }

        return {
            "scout_info": ctx,
            "keyboard": scout_info_kb()
        }
