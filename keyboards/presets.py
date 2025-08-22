from typing import List

from db.models import ActionStatus
from keyboards.spec import KeyboardSpec, KeyboardParams, RowOrName


def main_menu_kb() -> KeyboardSpec:
    return KeyboardSpec(
        type="inline",
        name="main_menu",
        options=["actions", "map", "news", "profile", "help"],
        params=KeyboardParams(max_in_row=2),
    )


def actions_menu_kb() -> KeyboardSpec:
    return KeyboardSpec(
        type="inline",
        name="actions_menu",
        options=["defend", "attack", "scout", "communicate", ["actions_list"], ["back"]],
        params=KeyboardParams(max_in_row=2)
    )


def district_list_kb() -> KeyboardSpec:
    return KeyboardSpec(
        type="inline",
        name="district_list_menu",
        options=[["prev", "next"], ["back"]],
        params=KeyboardParams(max_in_row=2),
        button_params={}
    )


def action_district_list_kb(action) -> KeyboardSpec:
    return KeyboardSpec(
        type="inline",
        name="action_district_menu",
        options=[["prev", "pick", "next"], ["back"]],
        params=KeyboardParams(max_in_row=2),
        button_params={
            "prev": {"action": action},
            "pick": {"action": action},
            "next": {"action": action},
            # "back" — без параметров
        },
    )


def action_setup_kb(resources: List[str], action_id: int, action_status: ActionStatus,
                    communicate=False, is_help=False) -> KeyboardSpec:
    """
    Строит inline-клавиатуру для настройки защиты.
    Для каждого ресурса добавляет ряд: <res>_remove | <res> | <res>_add
    В конце добавляется ряд с кнопкой 'back'.
    """
    rows: List[RowOrName] = list()
    if action_status is ActionStatus.DRAFT or action_status == "draft":
        if not communicate:
            if not is_help:
                rows.append(["collective", "individual"])
            for res in resources:
                res = res.strip()
                if not res:
                    continue
                rows.append([f"{res}_remove", res, f"{res}_add"])
            rows.append(["moving_on_point"])
            rows.append(["done"])
            rows.append(["delete", "back"])
        else:
            for res in resources:
                res = res.strip()
                if not res:
                    continue
                rows.append([f"{res}_remove", res, f"{res}_add"])
            rows.append(["done"])
            rows.append(["delete", "back"])

    elif action_status is ActionStatus.PENDING or action_status == "pending":
        if not communicate:
            rows.append(["edit"])
            rows.append(["delete", "back"])
        else:
            rows.append(["back"])
    else:
        rows.append(["back"])
    butns_kwargs = {row: {"action_id": action_id} for row in sum(rows, [])}

    return KeyboardSpec(
        type="inline",
        name="action_setup_menu",
        options=rows,
        params=KeyboardParams(max_in_row=3),
        button_params=butns_kwargs,
    )


def scout_choice_kb() -> KeyboardSpec:
    rows: List[RowOrName] = [["scout_district", "scout_info"], ["back"]]
    button_params = {
        "scout_district": {"action": "scout"},
        "scout_info": {"action": "scout"},
        # "back" без payload
    }
    return KeyboardSpec(
        type="inline",
        name="scout_menu",
        options=rows,
        params=KeyboardParams(max_in_row=2),
        button_params=button_params,
    )


def scout_info_kb() -> KeyboardSpec:
    return KeyboardSpec(
        type="inline",
        name="scout_info",
        options=[["back"]],  # одна кнопка назад
        params=KeyboardParams(max_in_row=1),
        button_params={}
    )


def communicate_kb() -> KeyboardSpec:
    # одна кнопка "back"
    return KeyboardSpec(
        type="inline",
        name="communicate_prompt",
        options=[["back"]],
        params=KeyboardParams(max_in_row=1),
    )


def news_list_kb(disabled: bool = False) -> KeyboardSpec:
    # prev/next, затем back
    opts = [["prev", "next"], ["back"]]
    # Можно, если надо, отключать prev/next когда disabled=True
    if disabled:
        opts = [["back"]]
    return KeyboardSpec(
        type="inline",
        name="news_list_menu",
        options=opts,
        params=KeyboardParams(max_in_row=2),
    )