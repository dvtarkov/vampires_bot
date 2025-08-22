# keyboards/presets_actions_stats.py
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from keyboards.spec import KeyboardSpec, KeyboardParams

StatusKey = Literal["draft", "pending", "success", "fail"]

_STATUS_TITLE = {
    "draft":   "Draft",
    "pending": "Pending",
    "success": "Success",
    "fail":    "Fail",
}


def actions_stats_kb(counts: Dict[StatusKey, int]) -> KeyboardSpec:
    """
    Кнопки: Draft (N) | Pending (N)
            Success (N) | Fail (N)
            Back
    Каждая из четырёх — вызывает option 'actions_stats_show' с payload {'status': <status_key>}
    """
    opts = [
        "draft", "pending",
        "success", "fail",
        "back"
    ]
    # подписи кнопок внутри шаблона не нужны — там текст; здесь только payload
    button_params = {
        "draft":   {"status": "draft"},
        "pending": {"status": "pending"},
        "success": {"status": "success"},
        "fail":    {"status": "fail"},
    }
    return KeyboardSpec(
        type="inline",
        name="actions_stats_menu",
        options=opts,
        params=KeyboardParams(max_in_row=2),
        button_params=button_params
    )


def actions_by_status_kb(*, status: StatusKey, page: int, has_prev: bool, has_next: bool) -> KeyboardSpec:
    """
    Кнопки: << Prev | Next >>     (если доступны)
            Back to Stats | Back to Actions
    """
    rows: List[List[str]] = []
    nav_row: List[str] = []
    if has_prev:
        nav_row.append("status_list_prev")
    if has_next:
        nav_row.append("status_list_next")
    if nav_row:
        rows.append(nav_row)
    rows.append(["status_list_back_stats", "status_list_back_actions"])

    button_params = {
        "status_list_prev":   {"status": status, "move": "prev", "page": page},
        "status_list_next":   {"status": status, "move": "next", "page": page},
        "status_list_back_stats":   {},
        "status_list_back_actions": {},
    }
    return KeyboardSpec(
        type="inline",
        name="actions_by_status_menu",
        options=rows,
        params=KeyboardParams(max_in_row=2),
        button_params=button_params
    )
