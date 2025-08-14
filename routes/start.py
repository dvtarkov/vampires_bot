import logging
from aiogram import Router, types
from aiogram.filters import Command, CommandStart

from screens.registration_screen import RegistrationScreen, RegistrationSuccessScreen
from db.session import get_session
from db.models import User


router = Router()


@router.message(CommandStart())
@router.message(Command("start"))
async def start_handler(message: types.Message, state):
    logging.info("Handling /start from user_id=%s", message.from_user.id)

    # на всякий очищаем предыдущие состояния
    try:
        await state.clear()
    except Exception:
        pass

    tg_id = message.from_user.id

    # достаём пользователя
    async with get_session() as session:
        user = await User.get_by_tg_id(session, tg_id)

    # если есть и имя уже задано — успех-экран; иначе — экран ввода имени
    if user and user.in_game_name:
        await RegistrationSuccessScreen().run(message=message, actor=message.from_user)
    else:
        await RegistrationScreen().run(message=message, actor=message.from_user, state=state)
