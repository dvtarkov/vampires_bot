import hashlib
import json
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup


def markup_to_tuple(markup) -> tuple | None:
    if markup is None:
        return None
    # Приведём к детерминированному виду (для сравнения)
    if isinstance(markup, InlineKeyboardMarkup):
        return tuple(tuple((b.text, getattr(b, "callback_data", None), getattr(b, "url", None)) for b in row)
                     for row in markup.inline_keyboard)
    if isinstance(markup, ReplyKeyboardMarkup):
        return tuple(tuple(b.text for b in row) for row in markup.keyboard)
    return None


def content_hash(text: str, markup) -> str:
    m = hashlib.sha256()
    m.update(text.encode("utf-8"))
    mt = markup_to_tuple(markup)
    if mt is not None:
        m.update(json.dumps(mt, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return m.hexdigest()
