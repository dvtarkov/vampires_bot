import logging
from aiogram import types

from keyboards.presets import actions_menu_kb
from .base import BaseScreen


class ActionsScreen(BaseScreen):
    async def _pre_render(self, message: types.Message, **kwargs):
        logging.info("ActionsScreen for user_id=%s", message.from_user.id)

        return {"keyboard": actions_menu_kb()}
