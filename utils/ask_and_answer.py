# utils/ask_and_answer.py
import os
from typing import Optional, Sequence
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

# колонки листа строго в таком порядке:
AA_HEADER: Sequence[str] = (
    "username", "in_game_name", "question", "answer", "answered", "sent_to_user"
)
NEW_HEADER: Sequence[str] = (
    "username", "in_game_name", "question", "answer", "answered", "sent_to_user", "action_id"
)
OLD_HEADER: Sequence[str] = (
    "username", "in_game_name", "question", "answer", "answered", "sent_to_user"
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def _ensure_header(ws: gspread.Worksheet) -> None:
    header = ws.row_values(1)

    # уже новый формат — ок
    if header == list(NEW_HEADER):
        return

    # если старый формат — расширим колонками и обновим шапку
    if header == list(OLD_HEADER):
        cur_cols = ws.col_count
        need_cols = len(NEW_HEADER)
        if cur_cols < need_cols:
            ws.add_cols(need_cols - cur_cols)
        ws.update("A1", [list(NEW_HEADER)])
        return

    # иначе просто выставляем правильную шапку (создастся/перезапишется)
    cur_cols = ws.col_count
    need_cols = len(NEW_HEADER)
    if cur_cols < need_cols:
        ws.add_cols(need_cols - cur_cols)
    ws.update("A1", [list(NEW_HEADER)])

def _open_ws(gc: gspread.Client, spreadsheet_id: str, title: str) -> gspread.Worksheet:
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1, cols=len(NEW_HEADER))
        ws.update("A1", [list(NEW_HEADER)])
        return ws

    _ensure_header(ws)
    return ws


def append_ask_and_answer(
    username: str,
    in_game_name: str,
    question: str,
    action_id: Optional[int] = None,
    *,
    spreadsheet_id: Optional[str] = None,
    service_account_path: Optional[str] = None,
) -> None:
    """
    Добавляет строку в лист 'ask_and_answer' с колонками:
    username, in_game_name, question, answer="", answered=FALSE, sent_to_user=FALSE, action_id
    """
    spreadsheet_id = spreadsheet_id or os.environ["SPREADSHEET_ID"]
    service_account_path = service_account_path or os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

    creds = Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
    gc = gspread.authorize(creds)

    ws = _open_ws(gc, spreadsheet_id, "ask_and_answer")

    row = [
        (username or "").strip(),
        (in_game_name or "").strip(),
        (question or "").strip(),
        "",        # answer
        "FALSE",   # answered
        "FALSE",   # sent_to_user
        str(action_id or ""),  # action_id (как текст; при желании можно писать числом)
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")


if __name__ == "__main__":
    append_ask_and_answer(
        username="NotThatDroids",
        in_game_name="Оракул",
        question="Можно ли перенести ритуал?",
        action_id=1234,
    )
