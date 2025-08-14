# text_dispatcher.py
import importlib
import pkgutil
from typing import Awaitable, Callable, Dict, Optional, Union

from aiogram.fsm.state import State

TextHandler = Callable[..., Awaitable[None]]
_REGISTRY: Dict[str, TextHandler] = {}  # key = state string


def _normalize_state_key(state: Union[State, str]) -> str:
    # aiogram v3: State.state -> "Package:state_name" (строка)
    if isinstance(state, State):
        return state.state
    return str(state)


def text_handler(state: Union[State, str]):
    """
    Декоратор: регистрирует функцию как обработчик текстов для указанного стейта.
    Пример: @text_handler(Registration.waiting_name)
    """
    key = _normalize_state_key(state)

    def wrapper(func: TextHandler):
        if key in _REGISTRY:
            raise RuntimeError(f"text_handler for state '{key}' already registered")
        _REGISTRY[key] = func
        return func

    return wrapper


def get_text_handler(state_key: str) -> Optional[TextHandler]:
    return _REGISTRY.get(state_key)


def load_all_text_handlers(package_name: str = "text_handlers"):
    """
    Импортирует все модули пакета text_handlers/* чтобы сработали декораторы.
    Вызвать один раз при старте.
    """
    pkg = importlib.import_module(package_name)
    for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        importlib.import_module(m.name)
