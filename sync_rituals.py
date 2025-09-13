# sync_rituals.py
import os
import asyncio
import logging
from typing import Sequence, Dict, Any

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from sqlalchemy import select
from sqlalchemy.orm import joinedload

# ========= ВАШИ ИМПОРТЫ БД (проверьте пути) =========
from db.session import get_session
from db.models import Action, User  # проверьте, что User у Action -> owner / user
from db.models import ActionStatus  # Enum со значениями PENDING, DONE
# ====================================================

# Опционально уведомление в Telegram
from aiogram import Bot


load_dotenv()
log = logging.getLogger("sync_rituals")
logging.basicConfig(level=logging.INFO)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ====== bot (как в game_cycle.py) ======
try:
    from app import bot  # type: ignore
except Exception:
    bot = None
    log.warning("Бот недоступен: уведомления отправлены не будут.")

# Ожидаем такая шапка листа (порядок не важен, ищем по названиям колонок):
# title | user | text | created_at | RESOLVED | action_id
EXPECTED_COLUMNS: Sequence[str] = ("title", "user", "text", "created_at", "RESOLVED", "action_id")

SHEET_ID = os.environ["SPREADSHEET_ID"]
CREDS_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
RITUALS_SHEET_TITLE = os.getenv("RITUALS_SHEET_TITLE", "rituals")


def _truthy(v: str) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y", "да", "ok"}


def _index_headers(ws) -> Dict[str, int]:
    """
    Возвращает map {'title': 0, 'user': 1, ...} по реальным индексам колонок (0-based).
    Бросит ValueError, если не найдена нужная колонка.
    """
    header = ws.row_values(1)
    name_to_idx: Dict[str, int] = {}
    for i, name in enumerate(header):
        key = name.strip()
        if key in EXPECTED_COLUMNS:
            name_to_idx[key] = i
    missing = [c for c in EXPECTED_COLUMNS if c not in name_to_idx]
    if missing:
        raise ValueError(f"В листе '{RITUALS_SHEET_TITLE}' отсутствуют колонки: {missing}. Найдены: {header}")
    return name_to_idx


async def _notify_user(bot: Bot, tg_id: int, action: Action) -> None:
    """
    Отправляет пользователю уведомление о завершении ритуала.
    """
    title = getattr(action, "title", "") or "Ритуал"
    txt = getattr(action, "text", "") or ""
    msg = (
        f"✨ Ваш ритуал завершён!\n\n"
        f"Ритуал в <{action.district.name}> на {action.candles} 🕯"
        f"{txt[:1000]}"  # ограничим, чтобы не улететь в лимиты
    )
    try:
        await bot.send_message(tg_id, msg, parse_mode="HTML")
    except Exception as e:
        log.warning("Не удалось отправить сообщение tg_id=%s: %s", tg_id, e)


async def main() -> int:
    # Инициализация Google Sheets
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)

    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(RITUALS_SHEET_TITLE)

    headers_idx = _index_headers(ws)
    # Считаем ВСЕ значения (в т.ч. пустые) и пройдём по строкам, начиная со 2-й
    values = ws.get_all_values()
    if len(values) <= 1:
        log.info("Лист пуст (нет строк кроме шапки).")
        return 0

    updated = 0
    skipped = 0
    not_found = 0
    not_pending = 0
    no_tg = 0
    no_id = 0

    async with get_session() as session:
        # Чтобы не делать по одному запросу на каждую строку — соберём action_id
        resolved_rows = []
        action_ids = []
        for r in values[1:]:
            try:
                resolved_flag = r[headers_idx["RESOLVED"]]
            except Exception:
                continue
            if not _truthy(resolved_flag):
                skipped += 1
                continue

            raw_id = r[headers_idx["action_id"]].strip() if len(r) > headers_idx["action_id"] else ""
            if not raw_id:
                no_id += 1
                continue
            try:
                aid = int(raw_id)
            except ValueError:
                no_id += 1
                continue

            resolved_rows.append(r)
            action_ids.append(aid)

        if not action_ids:
            log.info("Нет RESOLVED ритуалов к обработке.")
            return 0

        # Забираем действия пачкой
        q = await session.execute(
            select(Action)
            .options(joinedload(Action.owner))  # подгрузим владельца (User)
            .where(Action.id.in_(action_ids))
        )
        actions_by_id: Dict[int, Action] = {a.id: a for a in q.scalars().all()}

        # Обработка
        for r in resolved_rows:
            aid = int(r[headers_idx["action_id"]])
            action = actions_by_id.get(aid)
            if not action:
                not_found += 1
                continue

            if action.status != ActionStatus.PENDING:
                not_pending += 1
                continue

            action.status = ActionStatus.DONE  # PENDING -> DONE
            updated += 1

            # Уведомление
            usr = getattr(action, "owner", None) or getattr(action, "user", None)
            tg_id = getattr(usr, "tg_id", None) if usr else None
            if tg_id and bot:
                await _notify_user(bot, tg_id, action)
            elif not tg_id:
                no_tg += 1

        await session.commit()

    log.info("Готово. Обновлено: %s, пропущено (не RESOLVED): %s, не найдено: %s, не PENDING: %s, без tg_id: %s, без action_id: %s",
             updated, skipped, not_found, not_pending, no_tg, no_id)

    # Выведем немного в stdout, чтобы попало в /admin логи
    print(f"UPDATED={updated} SKIPPED={skipped} NOT_FOUND={not_found} NOT_PENDING={not_pending} NO_TG={no_tg} NO_ID={no_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
