# screens/district_list.py
import logging
from datetime import timezone
from typing import List, Optional
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from config import load_config
from db.session import get_session
from db.models import User, District, ActionStatus, ActionType, Action, Politician
from keyboards.spec import KeyboardSpec, KeyboardParams
from .base import BaseScreen
from keyboards.presets import district_list_kb, action_district_list_kb, action_setup_kb

config = load_config()


def make_support_link(bot_username: str, parent_id: int) -> str:
    return f"https://t.me/{bot_username}?start=support_{parent_id}"


def ideology_bar(value: int, size: int = 11) -> str:
    """Рисуем шкалу ▪/💠 по -5..+5 (value). Центр — 💠."""
    # value ∈ [-5..+5] -> позиция [0..10]
    pos = max(-5, min(5, int(value))) + 5
    left = "▪" * pos
    right = "▪" * (size - pos - 1)
    return f"{left}💠{right}"


class DistrictActionList(BaseScreen):
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        move: str | None = None,   # 'next' | 'prev' | None
        **kwargs
    ):
        action = kwargs.get("action")

        tg_id = actor.id if actor else message.from_user.id
        logging.info("DistrictList for tg_id=%s", tg_id)

        async with get_session() as session:
            # пользователь нам всё ещё может понадобиться для будущих прав
            user = await User.get_by_tg_id(session, tg_id)
            if not user:
                user = await User.create(
                    session=session,
                    tg_id=tg_id,
                    username=(actor or message.from_user).username,
                    first_name=(actor or message.from_user).first_name,
                    last_name=(actor or message.from_user).last_name,
                    language_code=(actor or message.from_user).language_code,
                )

            # ВСЕ районы, без фильтра owner_id
            rows: List[District] = (
                await session.execute(
                    select(District)
                    .options(selectinload(District.owner))       # если хочешь показывать владельца
                    .order_by(District.id)        # сортировка по имени/ид
                )
            ).scalars().all()

        if not rows:
            return {
                "district": None,
                "info": {"count": 0, "index": 0},
                "keyboard": district_list_kb(),
            }

        if state:
            data = await state.get_data()
            idx = int(data.get("district_list_index", 0))
        else:
            idx = 0
        # прокрутка
        if move == "next":
            idx = (idx + 1) % len(rows)
        elif move == "prev":
            idx = (idx - 1) % len(rows)

        # на всякий — clamp, если число районов изменилось
        if idx >= len(rows) or idx < 0:
            idx = 0

        if state:
            await state.update_data(district_list_index=idx)

        district = rows[idx]
        info = {"count": len(rows), "index": idx + 1}

        async with get_session() as session:
            pols = await Politician.by_district(session, district.id)


        politicians = [
            {
                "id": p.id,
                "name": p.name,
                "role_and_influence": p.role_and_influence,
                "ideology": p.ideology,
                "ideology_bar": ideology_bar(p.ideology),
                "influence": p.influence,
                "bonuses_penalties": p.bonuses_penalties or "",
            }
            for p in pols
        ]

        return {
            "district": district,
            "info": info,
            "politicians": politicians,
            "keyboard": action_district_list_kb(action)
        }


class SettingsActionScreen(BaseScreen):
    async def _pre_render(
        self,
        message: types.Message,
        actor: Optional[types.User] = None,
        state: Optional[FSMContext] = None,
        move: Optional[str] = None,             # 'next' | 'prev' | None
        is_list: bool = False,                  # режим списка
        statuses: Optional[List[str]] = None,   # фильтр по статусам ['draft','pending','done','failed']
        **kwargs
    ):
        tg_id = (actor or message.from_user).id
        logging.info(
            "SettingsActionScreen for tg_id=%s (is_list=%s, move=%s, statuses=%s)",
            tg_id, is_list, move, statuses
        )

        def human(dt):
            try:
                return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC") if dt else "—"
            except Exception:
                return "—"

        async with get_session() as session:
            # --- 1) Пользователь ---
            user = await User.get_by_tg_id(session, tg_id)
            if not user:
                user = await User.create(
                    session=session,
                    tg_id=tg_id,
                    username=(actor or message.from_user).username,
                    first_name=(actor or message.from_user).first_name,
                    last_name=(actor or message.from_user).last_name,
                    language_code=(actor or message.from_user).language_code,
                )

            # --- 2) Источник action: список / одиночный ---
            action_obj: Optional[Action] = kwargs.get("action")
            action_id: Optional[int] = kwargs.get("action_id")

            actions_list: List[Action] = []
            idx = 0

            if is_list:
                # Сохраним активный фильтр в FSM (чтобы prev/next учитывали его)
                if state:
                    await state.update_data(actions_list_statuses=statuses)

                query = (
                    select(Action)
                    .options(
                        selectinload(Action.support_actions),
                        selectinload(Action.parent_action),
                        selectinload(Action.owner),
                        selectinload(Action.district),
                    )
                    .where(Action.owner_id == user.id)
                    .order_by(Action.updated_at.desc(), Action.id.desc())
                )
                ALIASES = {
                    "success": "done",
                    "fail": "failed",
                }

                # Нормализуем статусы и применим фильтр
                if statuses:
                    norm: list[ActionStatus] = []
                    seen: set[ActionStatus] = set()

                    for s in statuses:
                        v = ALIASES.get(s.lower(), s.lower())
                        try:
                            st = ActionStatus(v)
                        except ValueError:
                            logging.warning("Unknown status filter: %s", s)
                            continue
                        if st not in seen:  # без дублей
                            norm.append(st)
                            seen.add(st)

                    if norm:
                        query = query.where(Action.status.in_(norm))

                actions_list = (await session.execute(query)).scalars().all()

                if not actions_list:
                    # Пустой список — отдаём минимальный экран
                    keyboard = KeyboardSpec(
                        type="inline",
                        name="action_setup_menu",
                        options=[["back"]],
                        params=KeyboardParams(max_in_row=1),
                        button_params={"back": {}},
                    )
                    return {
                        "action": {
                            "id": None,
                            "kind": None,
                            "title": None,
                            "status": "draft",
                            "type": "individual",
                            "owner": {"name": user.first_name or user.username or str(user.tg_id)},
                            "district": None,
                            "created_human": "—",
                            "updated_human": "—",
                            "resources": {"force": 0, "money": 0, "influence": 0, "information": 0},
                            "support": {"is_support": False, "parent_id": None, "parent_title": None, "children_count": 0},
                            "ui": {"show_type_switch": False, "show_district": False, "resources_editable": False},
                        },
                        "keyboard": keyboard,
                        "list_info": {"count": 0, "index": 0},
                    }

                # Индекс в списке
                data = await state.get_data() if state else {}
                idx = int(data.get("actions_list_index", 0))

                if move == "next":
                    idx = (idx + 1) % len(actions_list)
                elif move == "prev":
                    idx = (idx - 1) % len(actions_list)

                # Если пришёл action_id — позиционируемся на нём
                if action_id is not None:
                    for i, a in enumerate(actions_list):
                        if a.id == action_id:
                            idx = i
                            break

                # Границы
                if idx < 0 or idx >= len(actions_list):
                    idx = 0

                if state:
                    await state.update_data(actions_list_index=idx)

                action_obj = actions_list[idx]
            else:
                # Одиночный режим — достаём по id при необходимости
                if not action_obj and action_id:
                    action_obj = (
                        await session.execute(
                            select(Action)
                            .options(
                                selectinload(Action.support_actions),
                                selectinload(Action.parent_action),
                                selectinload(Action.owner),
                                selectinload(Action.district),
                            )
                            .where(Action.id == action_id)
                        )
                    ).scalars().first()

            # --- 3) Сбор контекста для шаблона ---
            if action_obj:
                district_name = action_obj.district.name if action_obj.district else None
                owner_name = (
                    action_obj.owner.in_game_name
                    or action_obj.owner.username
                    or str(user.tg_id)
                )

                support = {
                    "is_support": action_obj.parent_action_id is not None,
                    "parent_id": action_obj.parent_action_id,
                    "parent_title": action_obj.parent_action.title if action_obj.parent_action else None,
                    "children_count": len(action_obj.support_actions) if action_obj.support_actions is not None else 0,
                }

                status_str = action_obj.status.value if isinstance(action_obj.status, ActionStatus) else (action_obj.status or "draft")
                type_str = action_obj.type.value if isinstance(action_obj.type, ActionType) else (action_obj.type or "individual")

                action_ctx = {
                    "id": action_obj.id,
                    "kind": action_obj.kind,
                    "title": action_obj.title,
                    "status": status_str,
                    "type": type_str,
                    "owner": {"name": owner_name},
                    "district": {"name": district_name} if district_name else None,
                    "created_human": human(action_obj.created_at),
                    "updated_human": human(action_obj.updated_at),
                    "resources": {
                        "force": action_obj.force,
                        "money": action_obj.money,
                        "influence": action_obj.influence,
                        "information": action_obj.information,
                        "candles": getattr(action_obj, "candles", 0),  # ← добавлено
                    },
                    "support": support,
                    "ui": {
                        "show_type_switch": True,
                        "show_district": True,
                        "resources_editable": True,
                    },
                    "text": action_obj.text,
                }
            else:
                # Если вообще нечего показать — минимальный контекст + back
                keyboard = KeyboardSpec(
                    type="inline",
                    name="action_setup_menu",
                    options=[["back"]],
                    params=KeyboardParams(max_in_row=1),
                    button_params={"back": {}},
                )
                return {
                    "action": {
                        "id": None,
                        "kind": None,
                        "title": None,
                        "status": "draft",
                        "type": "individual",
                        "owner": {"name": user.first_name or user.username or str(user.tg_id)},
                        "district": None,
                        "created_human": "—",
                        "updated_human": "—",
                        "resources": {"force": 0, "money": 0, "influence": 0, "information": 0},
                        "support": {"is_support": False, "parent_id": None, "parent_title": None, "children_count": 0},
                        "ui": {"show_type_switch": False, "show_district": False, "resources_editable": False},
                    },
                    "keyboard": keyboard,
                }

        # --- 4) Ветвление по типу действия + клавиатура ---
        kind = (action_ctx["kind"] or "").lower()
        resources_for_kb = ["force", "money", "influence", "information"]

        # Ссылка для присоединения (только коллективные + pending)
        try:
            action_ctx["join_link"] = (
                make_support_link(config.bot_name, action_obj.id)
                if action_obj
                and action_obj.type == ActionType.COLLECTIVE
                and action_obj.status == ActionStatus.PENDING
                else None
            )
        except Exception:
            action_ctx["join_link"] = None

        # Клавиатура
        if kind in ("defend", "attack"):
            action_ctx["ui"]["show_type_switch"] = True
            action_ctx["ui"]["show_district"] = True
            action_ctx["ui"]["resources_editable"] = True

            is_help = (action_ctx.get("type") or "").lower() == "support"
            keyboard = action_setup_kb(
                resources_for_kb,
                action_ctx["id"],
                action_ctx["status"],
                is_help=is_help,
                is_list=is_list,
            )

        elif kind == "scout":
            action_ctx["ui"]["show_type_switch"] = False
            action_ctx["ui"]["show_district"] = False
            action_ctx["ui"]["resources_editable"] = False

            # Простая клавиатура (done/delete/back) + навигация
            opts = [["delete", "done"], ["back"]] if action_obj.status is ActionStatus.DRAFT else [["back"]]
            if is_list:
                opts.insert(0, ["prev", "next"])

            button_params = {btn: {"action_id": action_ctx["id"]} for btn in sum(opts, [])}
            if is_list:
                button_params["prev"] = {"is_list": True}
                button_params["next"] = {"is_list": True}

            keyboard = KeyboardSpec(
                type="inline",
                name="action_setup_menu",
                options=opts,
                params=KeyboardParams(max_in_row=2),
                button_params=button_params,
            )

        elif kind == "communicate":
            action_ctx["ui"]["show_type_switch"] = False
            action_ctx["ui"]["show_district"] = False
            action_ctx["ui"]["resources_editable"] = True

            resources_for_kb = ["information"]
            keyboard = action_setup_kb(
                resources_for_kb,
                action_ctx["id"],
                action_ctx["status"],
                communicate=True,
                is_list=is_list,
            )
        elif kind == "ritual":
            # как communicate, но главный ресурс — candles; район не выбираем
            action_ctx["ui"]["show_type_switch"] = False
            action_ctx["ui"]["show_district"] = False
            action_ctx["ui"]["resources_editable"] = True

            resources_for_kb = ["candles"]
            keyboard = action_setup_kb(
                resources_for_kb,
                action_ctx["id"],
                action_ctx["status"],
                is_list=is_list,
                communicate=True,
            )
        else:
            # запасной вариант — как defend
            keyboard = action_setup_kb(
                resources_for_kb,
                action_ctx["id"],
                action_ctx["status"],
                is_list=is_list,
            )

        # Информация о списке (для шаблона/отладки)
        list_info = None
        if is_list and actions_list:
            list_info = {"count": len(actions_list), "index": idx + 1}

        logging.info(
            "SettingsActionScreen ctx ready: id=%s kind=%s status=%s (is_list=%s, idx=%s, total=%s)",
            action_ctx.get("id"), action_ctx.get("kind"), action_ctx.get("status"),
            is_list, (idx + 1 if is_list else None), (len(actions_list) if is_list else None)
        )

        return {
            "action": action_ctx,
            "keyboard": keyboard,
            "list_info": list_info,
        }
