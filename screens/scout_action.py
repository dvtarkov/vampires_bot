import logging
from aiogram import types
from aiogram.fsm.context import FSMContext

from screens.base import BaseScreen
from keyboards.presets import scout_choice_kb


class ScoutActionScreen(BaseScreen):
    """
    Экран с описанием режима разведки и выбором сценария.
    """
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        **kwargs
    ):
        tg_id = (actor or message.from_user).id
        logging.info("ScoutActionScreen for tg_id=%s", tg_id)

        # Контекст для шаблона
        ctx = {
            "title": "🕵️ Разведка (Scout)",
            "lines": [
                "Вы можете потратить действие на разведку района ИЛИ задать вопрос мастерской группе.",
                "После создания заявку нельзя отменить или удалить.",
                "Необходимые ресурсы будут списаны с вас при отправке заявки.",
            ],
        }

        return {
            "scout": ctx,
            "keyboard": scout_choice_kb(),
        }
