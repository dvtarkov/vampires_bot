# states/communicate.py
from aiogram.fsm.state import StatesGroup, State


class Ritual(StatesGroup):
    waiting_ritual = State()
