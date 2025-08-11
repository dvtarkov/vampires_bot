from keyboards.spec import KeyboardSpec, KeyboardParams


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
        params=KeyboardParams(max_in_row=2),
    )
