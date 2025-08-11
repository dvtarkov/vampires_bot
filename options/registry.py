import asyncio
import importlib
import pkgutil
from typing import Callable, Awaitable, Dict, Optional

_REGISTRY: Dict[str, Callable[..., Awaitable[None]]] = {}


def option(name: Optional[str] = None):
    """
    Декоратор для регистрации обработчика опции.
    Если name не указан — используется имя функции.
    """

    def wrapper(func: Callable[..., Awaitable[None]]):
        key = name or func.__name__
        if key in _REGISTRY:
            raise RuntimeError(f"Option '{key}' already registered")
        _REGISTRY[key] = func
        return func

    return wrapper


def get_option(name: str) -> Optional[Callable[..., Awaitable[None]]]:
    return _REGISTRY.get(name)


def load_all_options():
    """
    Импортирует все модули в пакете 'options', чтобы сработали декораторы @option.
    Вызывать один раз при старте приложения.
    """
    pkg_name = "options"
    package = importlib.import_module(pkg_name)
    for m in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(m.name)
