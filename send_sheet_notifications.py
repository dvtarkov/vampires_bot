# send_sheet_notifications.py
import asyncio
import logging
import os

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from db.models import User
from services.notify import notify_user

load_dotenv()

# ===== ENV =====
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SA_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./game.db")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ===== logging =====
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("send_sheet_notifications")

# ===== bot (как в game_cycle.py) =====
try:
    from app import bot  # type: ignore
except Exception:
    bot = None
    log.warning("Бот недоступен: уведомления отправлены не будут.")

# ===== Sheets helpers =====
SHEET_NAME = "notify_users"
HEADER = ["username", "title", "body", "notify"]

def truthy(x) -> bool:
    if x is None:
        return False
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "да"}

def get_ws(gc: gspread.Client, spreadsheet_id: str, title: str) -> gspread.Worksheet:
    sh = gc.open_by_key(spreadsheet_id)
    return sh.worksheet(title)

def ensure_header(ws: gspread.Worksheet) -> None:
    row = ws.row_values(1)
    if row != HEADER:
        if row:
            ws.update("A1", [HEADER])
        else:
            ws.append_row(HEADER)

def idx(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        raise RuntimeError(f"В листе '{SHEET_NAME}' отсутствует колонка '{name}'")

# ===== core =====
async def send_sheet_notifications() -> None:
    # 1) Sheets
    creds = Credentials.from_service_account_file(SA_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = get_ws(gc, SPREADSHEET_ID, SHEET_NAME)
    ensure_header(ws)

    values = ws.get_all_values()
    if not values or len(values) == 1:
        log.info("[notify_users] пусто")
        return

    header, rows = values[0], values[1:]
    i_username = idx(header, "username")
    i_title    = idx(header, "title")
    i_body     = idx(header, "body")
    i_notify   = idx(header, "notify")

    # 2) DB session
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async_session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    to_clear_rows: list[int] = []

    async with async_session_factory() as session:
        for rnum, r in enumerate(rows, start=2):
            try:
                need_send = truthy(r[i_notify] if i_notify < len(r) else "")
                if not need_send:
                    continue

                username = (r[i_username] if i_username < len(r) else "").strip().lstrip("@")
                title    = (r[i_title] if i_title < len(r) else "").strip()
                body     = (r[i_body]  if i_body  < len(r) else "").strip()

                if not username:
                    log.warning("Строка %s: пустой username — пропуск", rnum)
                    continue
                if not title and not body:
                    log.warning("Строка %s: пустые title/body — пропуск", rnum)
                    continue
                if not bot:
                    log.warning("Строка %s: bot недоступен — пропуск отправки", rnum)
                    continue

                # 3) найдём пользователя по username
                q = await session.execute(select(User).where(User.username == username))
                user = q.scalars().first()
                if not user or not user.tg_id:
                    log.warning("Строка %s: пользователь @%s не найден/нет tg_id — пропуск", rnum, username)
                    continue

                # 4) отправка
                await notify_user(bot, user.tg_id, title=title or "Уведомление", body=body or "")

                # 5) сбросим флаг notify чтобы не слать повторно
                to_clear_rows.append(rnum)

            except Exception:
                log.exception("Ошибка обработки строки %s", rnum)

    # 6) массово проставим notify=FALSE
    if to_clear_rows:
        notify_col = chr(ord('A') + i_notify)  # колонка notify
        requests = [{"range": f"{notify_col}{row}", "values": [["FALSE"]]} for row in to_clear_rows]
        ws.batch_update(requests, value_input_option="USER_ENTERED")
        log.info("Отметок notify сброшено: %d строк", len(to_clear_rows))
    else:
        log.info("Новых уведомлений для отправки не найдено.")

async def main():
    await send_sheet_notifications()

if __name__ == "__main__":
    asyncio.run(main())
