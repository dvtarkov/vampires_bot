import logging
from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.base import BaseScreen
from keyboards.presets import communicate_kb
from states.ritual import Ritual


class RitualScreen(BaseScreen):
    """
    Просит прислать текст ритуала.
    Ставит FSM в Ritual.waiting_ritual.
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
        logging.info("RitualScreen for tg_id=%s", user.id)

        if state:
            await state.set_state(Ritual.waiting_ritual)

        ctx = {
            "title": "Начать ритуал",
            "lines": [
                "Пришлите место проведения ритуала вместе с ссылкой на актуальное положение на гугл-картах одним сообщением.",
                "Эта заявка создаст действие «ritual» (без района).",
                "Текст будет записан и после этого вы попадёте в экран настройки заявки.",
            ],
            "hint": "Отправьте информацию о ритуале (от 1 до 600 символов):",
            "error_text": error_text,   # опционально показываем ошибку
        }

        return {
            "ritual": ctx,
            "keyboard": communicate_kb()
        }
