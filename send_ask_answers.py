# send_ask_answers.py
import asyncio
import logging
import os
from sqlalchemy import select, update
from db.models import User, Action, ActionStatus
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from db.models import User
from services.notify import notify_user

load_dotenv()

# ====== ENV ======
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SA_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./game.db")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ====== logging ======
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("send_ask_answers")

# ====== bot (как в game_cycle.py) ======
try:
    from app import bot  # type: ignore
except Exception:
    bot = None
    log.warning("Бот недоступен: уведомления отправлены не будут.")

# ====== Sheets helpers ======
SHEET_NAME = "ask_and_answer"
HEADER = ["username", "in_game_name", "question", "answer", "answered", "sent_to_user", "action_id"]


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


# ====== core ======
async def send_ready_answers():
    # 1) Sheets
    creds = Credentials.from_service_account_file(SA_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = get_ws(gc, SPREADSHEET_ID, SHEET_NAME)
    ensure_header(ws)

    values = ws.get_all_values()
    if not values or len(values) == 1:
        log.info("[ask_and_answer] пусто")
        return

    header, rows = values[0], values[1:]
    i_username = idx(header, "username")
    i_question = idx(header, "question")
    i_answer = idx(header, "answer")
    i_answered = idx(header, "answered")
    i_sent = idx(header, "sent_to_user")
    i_action = header.index("action_id") if "action_id" in header else None  # опционально

    # 2) DB session
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async_session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    marked_rows: list[int] = []
    to_close_action_ids: list[int] = []

    async with async_session_factory() as session:
        for rnum, r in enumerate(rows, start=2):
            try:
                answered = truthy(r[i_answered] if i_answered < len(r) else "")
                already_sent = truthy(r[i_sent] if i_sent < len(r) else "")
                if not answered or already_sent:
                    continue

                username = (r[i_username] if i_username < len(r) else "").strip().lstrip("@")
                question = (r[i_question] if i_question < len(r) else "").strip()
                answer = (r[i_answer] if i_answer < len(r) else "").strip()

                if not username:
                    log.warning("Строка %s: пустой username — пропуск", rnum)
                    continue
                if not answer:
                    log.warning("Строка %s: answered=TRUE, но пустой answer — пропуск", rnum)
                    continue

                # 3) найдём пользователя по username
                q = await session.execute(select(User).where(User.username == username))
                user = q.scalars().first()
                if not user or not user.tg_id:
                    log.warning("Строка %s: пользователь @%s не найден/нет tg_id — пропуск", rnum, username)
                    continue

                if not bot:
                    log.warning("Строка %s: bot недоступен — пропуск отправки", rnum)
                    continue

                # 4) уведомление
                title = "Ответ на вопрос"
                body = f"Ответ на вопрос: {question}\n\n{answer}"
                await notify_user(bot, user.tg_id, title=title, body=body)

                # 5) отметить в таблице как отправленное
                marked_rows.append(rnum)

                # 6) собрать action_id для закрытия (если есть)
                if i_action is not None and i_action < len(r):
                    raw = (r[i_action] or "").strip()
                    if raw:
                        try:
                            aid = int(raw)
                            to_close_action_ids.append(aid)
                        except ValueError:
                            log.warning("Строка %s: некорректный action_id='%s' — пропуск закрытия", rnum, raw)

            except Exception:
                log.exception("Ошибка обработки строки %s", rnum)

        # 7) закрыть экшены единым апдейтом
        if to_close_action_ids:
            await session.execute(
                update(Action)
                .where(Action.id.in_(to_close_action_ids))
                .values(status=ActionStatus.DONE, updated_at=datetime.now(timezone.utc))
            )
            await session.commit()
            log.info("Экшенов переведено в DONE: %d", len(to_close_action_ids))

    # 8) массово проставим sent_to_user=TRUE в гугл-таблице
    if marked_rows:
        sent_col = chr(ord('A') + i_sent)  # колонка sent_to_user
        requests = [{"range": f"{sent_col}{row}", "values": [["TRUE"]]} for row in marked_rows]
        ws.batch_update(requests, value_input_option="USER_ENTERED")
        log.info("Отмечено как отправленные: %d строк", len(marked_rows))
    else:
        log.info("Новых ответов для отправки не найдено.")


async def main():
    await send_ready_answers()


if __name__ == "__main__":
    asyncio.run(main())
