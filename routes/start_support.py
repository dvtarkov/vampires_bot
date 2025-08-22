# routes/start_support.py
import logging
from aiogram import types, Router
from aiogram.filters import CommandStart, CommandObject
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, Action, ActionType, ActionStatus
from screens.registration_screen import RegistrationScreen, RegistrationSuccessScreen
from screens.settings_action import SettingsActionScreen

router = Router()

