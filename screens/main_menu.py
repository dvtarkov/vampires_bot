import logging
from aiogram import types

from keyboards.presets import main_menu_kb
from .base import BaseScreen
from keyboards.spec import KeyboardSpec, KeyboardParams


class MainMenuScreen(BaseScreen):
    async def _pre_render(self, message: types.Message, **kwargs):
        logging.info("MainMenuScreen for user_id=%s", message.from_user.id)

        return {"keyboard": main_menu_kb()}
