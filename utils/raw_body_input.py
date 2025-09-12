# add_raw_row_min.py
from datetime import datetime
import os
from typing import Optional, Dict, List

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

RAW_HEADER_CANON = ["id","title","raw_body","body","created_at","to_send","type","sent_at"]
ALIAS_MAP = {"type": {"type", "Type", "TYPE"}}

def _getenv_required(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"ENV '{key}' не задан. Добавьте его в .env или установите в окружении.")
    return v

def _authorize() -> gspread.Client:
    load_dotenv()
    sa_path = _getenv_required("GOOGLE_APPLICATION_CREDENTIALS")
    creds = Credentials.from_service_account_file(
        sa_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def _open_ws(gc: gspread.Client, title: str) -> gspread.Worksheet:
    spreadsheet_id = _getenv_required("SPREADSHEET_ID")
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1, cols=len(RAW_HEADER_CANON))
        ws.append_row(RAW_HEADER_CANON)
        return ws

    header = ws.row_values(1)
    if not header:
        ws.update("A1", [RAW_HEADER_CANON])
        header = RAW_HEADER_CANON

    # валидация наличия ключевых колонок
    must_have = {"raw_body", "type"}
    hdr_lc = {h.lower() for h in header}
    has_type = any(h.lower() in ALIAS_MAP["type"] for h in header)
    if not must_have.issubset(hdr_lc) and not has_type:
        raise RuntimeError(f"Лист '{title}' должен содержать колонки хотя бы raw_body и type. Сейчас: {header}")
    return ws


def add_raw_row(*, raw_body: str, type_value: str, created_at="") -> int:
    """
    Добавляет строку в лист RAW, заполняя ТОЛЬКО raw_body и type.
    Остальные поля (title, created_at, to_send, sent_at и т.д.) остаются пустыми.
    Возвращает 1-based номер добавленной строки.
    """
    gc = _authorize()
    ws = _open_ws(gc, "RAW")

    header = ws.row_values(1)
    header_lc = [h.lower() for h in header]

    # значения по умолчанию — пусто для всех колонок
    row_vals: Dict[str, str] = {h.lower(): "" for h in header}
    # заполняем только нужные
    row_vals["raw_body"] = raw_body or ""
    row_vals["created_at"] = created_at or ""
    # учтём любые варианты регистра колонки type
    for h, h_lc in zip(header, header_lc):
        if h_lc in ALIAS_MAP["type"]:
            row_vals[h_lc] = type_value or ""

    # собрать строку в порядке текущего хедера
    out_row: List[str] = [row_vals.get(h_lc, "") for h_lc in header_lc]

    ws.append_row(out_row, value_input_option="USER_ENTERED")
    return len(ws.get_all_values())


# пример
if __name__ == "__main__":
    n = add_raw_row(
        raw_body=(
            "Захватил район <b>{user.name}</b>\n"
            "Прорыв силой <b>{power_pts}</b>\n"
            "Против защиты <b>{defend_pts}</b>\n"
            "Остаток <b>{overflow}</b> стал обороной района."
        ),
        type_value="event.capture",
    )
    print("Добавлено, строка №", n)
