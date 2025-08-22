# states/scout.py
from aiogram.fsm.state import StatesGroup, State

class Scout(StatesGroup):
    waiting_question = State()
