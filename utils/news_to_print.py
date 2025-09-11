# utils/news_to_print.py
import os
from datetime import datetime
from typing import Optional, List, Dict

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

NEWS_PRINT_HEADER = ["title", "body", "created_at", "to_send", "action_id", "spent_info"]

def _getenv_required(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"ENV '{key}' не задан. Добавьте в .env: {key}=...")
    return v

def _authorize() -> gspread.Client:
    load_dotenv()
    creds = Credentials.from_service_account_file(
        _getenv_required("GOOGLE_APPLICATION_CREDENTIALS"),
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def _open_news_to_print(gc: gspread.Client) -> gspread.Worksheet:
    sh = gc.open_by_key(_getenv_required("SPREADSHEET_ID"))
    title = "news_to_print"
    try:
        ws = sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1, cols=len(NEWS_PRINT_HEADER))
        ws.append_row(NEWS_PRINT_HEADER)
        return ws

    header = ws.row_values(1)
    # если шапка пустая — поставим нужную
    if not header:
        ws.update("A1", [NEWS_PRINT_HEADER])
        return ws

    # мягкая «починка»: добавим недостающие колонки в конец
    header_lc = [h.strip() for h in header]
    missing = [c for c in NEWS_PRINT_HEADER if c not in header_lc]
    if missing:
        new_header = header_lc + missing
        ws.update("A1", [new_header])
    return ws


def add_news_to_print(
    *,
    title: str,
    body: str,
    action_id: Optional[int] = None,
    spent_info: Optional[int] = None,
    to_send: bool = True,
    created_at: Optional[str] = None,
) -> int:
    """
    Добавляет строку в лист 'news_to_print' с полями:
    title | body | created_at | to_send | action_id | spent_info

    Возвращает 1-based номер добавленной строки.
    """
    gc = _authorize()
    ws = _open_news_to_print(gc)

    # финальный порядок берём из текущей шапки (мог добавиться «хвост»)
    header = ws.row_values(1)
    header = header if header else NEWS_PRINT_HEADER

    row_map: Dict[str, str] = {
        "title": title or "",
        "body": body or "",
        "created_at": created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "to_send": "TRUE" if to_send else "FALSE",
        "action_id": "" if action_id is None else str(action_id),
        "spent_info": "" if spent_info is None else str(spent_info),
    }

    # соберём строку по текущему порядку хедера; незнакомые поля оставляем пустыми
    out_row: List[str] = [row_map.get(col, "") for col in header]

    ws.append_row(out_row, value_input_option="USER_ENTERED")
    # номер последней строки = количество непустых строк
    return len(ws.get_all_values())

# пример использования:
if __name__ == "__main__":
    n = add_news_to_print(
        title="Игрок предложил новость",
        body="В районе Подбара заметили рост активности...",
        action_id=123,
        spent_info=5,     # сколько инфы потрачено игроком, если применимо
        to_send=True,     # сразу готово к переносу в лист 'news'
        # created_at="2025-09-10 03:23:06"  # можно задать вручную, иначе проставится текущее
    )
    print("Добавлено, строка №", n)
