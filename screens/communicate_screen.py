# screens/communicate_screen.py
import logging
from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.base import BaseScreen
from states.communicate import Communicate
from keyboards.presets import communicate_kb


class CommunicateScreen(BaseScreen):
    """
    Просит прислать текст новости для предложения.
    Ставит FSM в Communicate.waiting_news.
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
        logging.info("CommunicateScreen for tg_id=%s", user.id)

        if state:
            await state.set_state(Communicate.waiting_news)

        ctx = {
            "title": "🗞️ Предложить новость",
            "lines": [
                "Пришлите текст новости одним сообщением.",
                "Эта заявка создаст действие «communicate» (без района).",
                "Текст будет записан в поле action.text и после этого вы попадёте в экран настройки заявки.",
            ],
            "hint": "Отправьте новость (от 1 до 600 символов):",
            "error_text": error_text,   # опционально показываем ошибку
        }

        return {
            "communicate": ctx,
            "keyboard": communicate_kb()
        }
