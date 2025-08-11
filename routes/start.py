import logging
from aiogram import Router, types
from aiogram.filters import Command, CommandStart

from screens.main_menu import MainMenuScreen

router = Router()


@router.message(CommandStart())
@router.message(Command("start"))
async def start_handler(message: types.Message):
    logging.info("Handling /start from user_id=%s", message.from_user.id)
    await MainMenuScreen().run(message=message)
