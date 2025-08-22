# states/communicate.py
from aiogram.fsm.state import StatesGroup, State


class Communicate(StatesGroup):
    waiting_news = State()
