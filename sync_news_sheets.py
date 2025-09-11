# sync_news_sheets.py
import os
import re
import logging
import asyncio
from typing import List, Set, Tuple, Optional

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update

from db.session import Base  # noqa
from db.models import Action, ActionStatus, User
from services.notify import notify_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("sync_news")

# ─────────── ENV / GS ───────────
load_dotenv()
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SA_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
DB_URL = os.environ["DATABASE_URL"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# ─────────── Utils ───────────
def norm_text(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\u00A0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def make_key(title: str, body: str) -> str:
    return norm_text(title) + "\n" + norm_text(body)

def truthy(x) -> bool:
    if x is None:
        return False
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "да"}

def get_ws(gc: gspread.Client, spreadsheet_id: str, title: str) -> gspread.Worksheet:
    sh = gc.open_by_key(spreadsheet_id)
    return sh.worksheet(title)

NEEDED_NEWS_HEADER = ["id","title","body","media_urls","action_id","created_at","updated_at","action__name"]

def ensure_news_header(ws_news):
    header = ws_news.row_values(1)
    if header != NEEDED_NEWS_HEADER:
        if header:
            ws_news.update("A1", [NEEDED_NEWS_HEADER])
        else:
            ws_news.append_row(NEEDED_NEWS_HEADER)

def append_rows_news(ws_news, rows):
    if rows:
        ws_news.append_rows(rows, value_input_option="USER_ENTERED")

def existing_news_keys(ws_news) -> Set[str]:
    rows = ws_news.get_all_values()
    if not rows:
        return set()
    header, data = rows[0], rows[1:]
    try:
        i_title = header.index("title")
        i_body  = header.index("body")
    except ValueError:
        return set()
    keys = set()
    for r in data:
        t = r[i_title] if i_title < len(r) else ""
        b = r[i_body]  if i_body  < len(r) else ""
        if t or b:
            keys.add(make_key(t, b))
    return keys

# ─────────── Перенос: news_to_print → news ───────────
def sync_news_to_print_to_news(gc) -> Tuple[int, List[int]]:
    """
    Возвращает (сколько добавлено, список action_id для постобработки).
    """
    ws_src = get_ws(gc, SPREADSHEET_ID, "news_to_print")
    ws_dst = get_ws(gc, SPREADSHEET_ID, "news")

    ensure_news_header(ws_dst)
    already = existing_news_keys(ws_dst)

    data = ws_src.get_all_values()
    if not data:
        log.info("[news_to_print] пусто")
        return 0, []

    header, rows = data[0], data[1:]

    def idx(name):
        try: return header.index(name)
        except ValueError: return None

    i_title   = idx("title")
    i_body    = idx("body")
    i_send    = idx("to_send")
    i_action  = idx("action_id")

    if i_title is None or i_body is None or i_send is None:
        raise RuntimeError("news_to_print должен содержать: title, body, to_send")

    out, action_ids = [], []
    for r in rows:
        if not truthy(r[i_send] if i_send is not None and i_send < len(r) else ""):
            continue

        title = r[i_title] if i_title is not None and i_title < len(r) else ""
        body  = r[i_body]  if i_body  is not None and i_body  < len(r) else ""
        key   = make_key(title, body)

        if key in already:
            continue
        already.add(key)

        out.append(["", title, body, "[]", "", "", "", ""])

        if i_action is not None and i_action < len(r):
            s = str(r[i_action]).strip()
            if s:
                try:
                    action_ids.append(int(s))
                except Exception:
                    pass

    append_rows_news(ws_dst, out)
    log.info("[OK] news_to_print → news: добавлено %d", len(out))
    return len(out), action_ids

# ─────────── Перенос: RAW → news ───────────
def sync_raw_to_news(gc) -> int:
    ws_src = get_ws(gc, SPREADSHEET_ID, "RAW")
    ws_dst = get_ws(gc, SPREADSHEET_ID, "news")

    ensure_news_header(ws_dst)
    already = existing_news_keys(ws_dst)

    data = ws_src.get_all_values()
    if not data:
        log.info("[RAW] пусто")
        return 0

    header, rows = data[0], data[1:]

    def idx(name):
        try: return header.index(name)
        except ValueError: return None

    i_title  = idx("title")
    i_body   = idx("body")
    i_send_a = idx("to_send")
    i_send_b = idx("to_sent")
    i_send   = i_send_a if i_send_a is not None else i_send_b

    if i_title is None or i_body is None or i_send is None:
        raise RuntimeError("RAW должен содержать: title, body и to_send/to_sent")

    out = []
    for r in rows:
        if not truthy(r[i_send] if i_send < len(r) else ""):
            continue
        title = r[i_title] if i_title < len(r) else ""
        body  = r[i_body]  if i_body  < len(r) else ""
        key   = make_key(title, body)

        if key in already:
            continue
        already.add(key)

        out.append(["", title, body, "[]", "", "", "", ""])

    append_rows_news(ws_dst, out)
    log.info("[OK] RAW → news: добавлено %d", len(out))
    return len(out)

# ─────────── Пост-обработка: DONE + уведомления ───────────
async def process_actions_done_and_notify(session: AsyncSession, action_ids: List[int]) -> None:
    if not action_ids:
        return
    uniq_ids = sorted({int(a) for a in action_ids if a is not None})
    if not uniq_ids:
        return

    # пробуем получить бота как в game_cycle.py
    try:
        from app import bot  # type: ignore
    except Exception:
        bot = None
        log.warning("Бот недоступен: уведомления news_accepted отправляться не будут.")

    # достаём actions + owners
    res = await session.execute(
        select(Action, User.tg_id)
        .join(User, User.id == Action.owner_id)
        .where(Action.id.in_(uniq_ids))
    )
    rows = res.all()
    if not rows:
        return

    # 1) выставляем DONE пачкой
    ids_to_done = [a.id for a, _ in rows if a.status != ActionStatus.DONE]
    if ids_to_done:
        await session.execute(
            update(Action)
            .where(Action.id.in_(ids_to_done))
            .values(status=ActionStatus.DONE)
            .execution_options(synchronize_session="fetch")
        )
        await session.commit()
        log.info("Action → DONE: %d шт.", len(ids_to_done))

    # 2) уведомления авторам (если бот доступен)
    if bot:
        for a, user_tg_id in rows:
            try:
                await notify_user(
                    bot=bot,
                    user_tg_id=int(user_tg_id),
                    title="📰 Новость принята",
                    body="Ваше предложение добавлено в очередь публикации.",
                    parse_mode="HTML",
                    persist_key=f"news_accepted:{a.id}",
                )
            except Exception:
                log.exception("notify failed (action_id=%s)", a.id)

# ─────────── main ───────────
async def amain():
    creds = Credentials.from_service_account_file(SA_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)

    engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    added_np, action_ids = sync_news_to_print_to_news(gc)
    added_raw = sync_raw_to_news(gc)

    if action_ids:
        async with Session() as session:
            await process_actions_done_and_notify(session, action_ids)

    await engine.dispose()
    log.info("Готово: из news_to_print=%d, из RAW=%d", added_np, added_raw)

def main():
    asyncio.run(amain())

if __name__ == "__main__":
    main()
