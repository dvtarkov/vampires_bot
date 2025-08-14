# text_handlers/register_name.py
import logging
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from db.session import get_session
from db.models import User
from text_handlers import text_handler
from states.registration import Registration
from screens.registration_screen import RegistrationErrorScreen, RegistrationSuccessScreen


@text_handler(Registration.waiting_name)
async def handle_registration_name(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        if not raw:
            raise ValueError("Пустая строка.")
        if len(raw) > 150:
            raise ValueError("Слишком длинно. Максимум 150 символов.")

        tg_id = message.from_user.id
        async with get_session() as session:
            user = await User.get_by_tg_id(session, tg_id)
            if not user:
                user = await User.create(
                    session=session,
                    tg_id=tg_id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    language_code=message.from_user.language_code,
                )
            ok = await User.update_by_tg_id(session, tg_id, in_game_name=raw)
            if not ok:
                raise RuntimeError("Не удалось сохранить имя. Попробуйте ещё раз.")

        await RegistrationSuccessScreen().run(message=message, actor=message.from_user)

    except Exception as e:
        logging.exception("Registration failed")
        await RegistrationErrorScreen().run(
            message=message,
            actor=message.from_user,
            error_text=str(e) or "Неизвестная ошибка",
            state=state
        )
