from typing import List

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


def action_setup_kb(resources: List[str]) -> KeyboardSpec:
    """
    Строит inline-клавиатуру для настройки защиты.
    Для каждого ресурса добавляет ряд: <res>_remove | <res> | <res>_add
    В конце добавляется ряд с кнопкой 'back'.
    """
    rows: List[RowOrName] = [["collective", "individual"]]
    for res in resources:
        res = res.strip()
        if not res:
            continue
        rows.append([f"{res}_remove", res, f"{res}_add"])
    rows.append(["moving_on_point"])
    rows.append(["back"])

    return KeyboardSpec(
        type="inline",
        name="action_setup_kb",
        options=rows,
        params=KeyboardParams(max_in_row=3),
        button_params={},  # можно добавить параметры для отдельных кнопок при необходимости
    )
