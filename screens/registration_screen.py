from states.registration import Registration
import logging
from aiogram import types
from aiogram.fsm.context import FSMContext
from .base import BaseScreen


class RegistrationScreen(BaseScreen):
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        **kwargs
    ):
        user = actor or message.from_user
        logging.info("RegistrationScreen for tg_id=%s", user.id)
        if state:
            await state.set_state(Registration.waiting_name)

        return {
            "hint": kwargs.get("hint") or "Введите ваше игровое имя (до 150 символов):",
            "force_new": True
        }


class RegistrationErrorScreen(BaseScreen):
    """
    Показывает ошибку и снова просит ввести имя.
    """
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        error_text: str | None = None,
        **kwargs
    ):
        logging.info("RegistrationErrorScreen for tg_id=%s", (actor or message.from_user).id)

        # Снова ставим ожидание текста (после любого ввода state уже очищен глобальным хэндлером)
        if state:
            logging.info("State changing")
            await state.set_state(Registration.waiting_name)
            logging.info(str(state))

        return {
            "error_text": error_text or "Некорректный ввод.",
            "hint": "Попробуйте снова: введите игровое имя (до 150 символов).",
            "force_new": True
        }


class RegistrationSuccessScreen(BaseScreen):
    """
    Сообщает об успешной «пререгистрации».
    """
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        **kwargs
    ):
        logging.info("RegistrationSuccessScreen for tg_id=%s", (actor or message.from_user).id)
        return {
            "force_new": True
        }
