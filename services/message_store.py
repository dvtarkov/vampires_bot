from __future__ import annotations
import time
from typing import Optional, Dict, Tuple

# Ключ = (chat_id, persist_key, kind), где kind: "main" | "notice"
_Store: Dict[Tuple[int, str, str], Tuple[int, float, str]] = {}
# value = (message_id, ts, content_hash)

def set_message(chat_id: int, persist_key: str, kind: str, message_id: int, content_hash: str) -> None:
    _Store[(chat_id, persist_key, kind)] = (message_id, time.time(), content_hash)

def get_message(chat_id: int, persist_key: str, kind: str) -> Optional[Tuple[int, float, str]]:
    return _Store.get((chat_id, persist_key, kind))

def clear_message(chat_id: int, persist_key: str, kind: str) -> None:
    _Store.pop((chat_id, persist_key, kind), None)
