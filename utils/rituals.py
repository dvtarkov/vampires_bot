# utils/rituals.py
import os
from typing import Optional, Sequence
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

# Шапка листа "rituals" строго в таком виде и порядке:
RITUALS_HEADER: Sequence[str] = (
    "title",
    "user",
    "text",
    "created_at",
    "RESOLVED",
    "action_id"
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


def _ensure_header(ws: gspread.Worksheet, header: Sequence[str]) -> None:
    current = ws.row_values(1)

    # если шапка совпадает — ничего не делаем
    if current == list(header):
        return

    # иначе выставляем правильную шапку (создастся/перезапишется)
    cur_cols = ws.col_count
    need_cols = len(header)
    if cur_cols < need_cols:
        ws.add_cols(need_cols - cur_cols)
    ws.update("A1", [list(header)])


def _open_ws(gc: gspread.Client, spreadsheet_id: str, title: str, header: Sequence[str]) -> gspread.Worksheet:
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1, cols=len(header))
        ws.update("A1", [list(header)])
        return ws

    _ensure_header(ws, header)
    return ws


def append_ritual(
    *,
    action_title: str,
    action_user_in_game_name: str,
    action_text: str,
    spreadsheet_id: Optional[str] = None,
    service_account_path: Optional[str] = None,
    worksheet_title: str = "rituals",
    created_at: str = None,
    action_id: int = None
) -> None:
    """
    Добавляет строку в лист 'rituals' с колонками:
    action.title, action.user.in_game_name, action.text, RESOLVED
    """
    spreadsheet_id = spreadsheet_id or os.environ["SPREADSHEET_ID"]
    service_account_path = service_account_path or os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

    creds = Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
    gc = gspread.authorize(creds)

    ws = _open_ws(gc, spreadsheet_id, worksheet_title, RITUALS_HEADER)

    row = [
        (action_title or "").strip(),
        (action_user_in_game_name or "").strip(),
        (action_text or "").strip(),
        str(created_at),
        "FALSE",
        action_id
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")


if __name__ == "__main__":
    append_ritual(
        action_title="Перенос ритуала",
        action_user_in_game_name="Оракул",
        action_text="Прошу перенести ритуал на завтра из-за занятости.",
        created_at="created_at",
        action_id=1234123,
    )
