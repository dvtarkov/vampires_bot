# screens/district_list.py
import logging
from datetime import timezone
from typing import List
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from config import load_config
from db.session import get_session
from db.models import User, District, ActionStatus, ActionType, Action
from keyboards.spec import KeyboardSpec, KeyboardParams
from .base import BaseScreen
from keyboards.presets import district_list_kb, action_district_list_kb, action_setup_kb

config = load_config()


def make_support_link(bot_username: str, parent_id: int) -> str:
    return f"https://t.me/{bot_username}?start=support_{parent_id}"


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
        print(f"ACTION: {action}")

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
                    .order_by(District.name, District.id)        # сортировка по имени/ид
                )
            ).scalars().all()

        if not rows:
            return {
                "district": None,
                "info": {"count": 0, "index": 0},
                "keyboard": district_list_kb(),
            }

        # индекс из FSM
        idx = 0
        if state:
            data = await state.get_data()
            idx = int(data.get("district_list_index", 0))

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

        return {
            "district": district,
            "info": info,
            "keyboard": action_district_list_kb(action)
        }


class SettingsActionScreen(BaseScreen):
    async def _pre_render(
        self,
        message: types.Message,
        actor: types.User | None = None,
        state: FSMContext | None = None,
        move: str | None = None,
        **kwargs
    ):
        tg_id = actor.id if actor else message.from_user.id
        logging.info("DefendActionScreen for tg_id=%s", tg_id)

        def human(dt):
            try:
                return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC") if dt else "—"
            except Exception:
                return "—"

        async with get_session() as session:
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

            action_obj: Action | None = kwargs.get("action")
            action_id: int | None = kwargs.get("action_id")
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

            # ---- собрать контекст ----
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

                action_ctx = {
                    "id": action_obj.id,
                    "kind": action_obj.kind,
                    "title": action_obj.title,
                    "status": action_obj.status.value if isinstance(action_obj.status, ActionStatus) else (action_obj.status or "draft"),
                    "type": action_obj.type.value if isinstance(action_obj.type, ActionType) else (action_obj.type or "individual"),
                    "owner": {"name": owner_name},
                    "district": {"name": district_name} if district_name else None,
                    "created_human": human(action_obj.created_at),
                    "updated_human": human(action_obj.updated_at),
                    "resources": {
                        "force": action_obj.force,
                        "money": action_obj.money,
                        "influence": action_obj.influence,
                        "information": action_obj.information,
                    },
                    "support": support,
                    "ui": {  # UI-флаги для шаблона; значениями займёмся ниже
                        "show_type_switch": True,
                        "show_district": True,
                        "resources_editable": True,
                    },
                }
            else:
                action_ctx = {
                    "id": None,
                    "kind": "defend",
                    "title": kwargs.get("title"),
                    "status": ActionStatus.PENDING.value,
                    "type": ActionType.INDIVIDUAL.value,
                    "owner": {"name": user.first_name or user.username or str(user.tg_id)},
                    "district": None,
                    "created_human": "—",
                    "updated_human": "—",
                    "resources": {
                        "force": kwargs.get("force", 0),
                        "money": kwargs.get("money", 0),
                        "influence": kwargs.get("influence", 0),
                        "information": kwargs.get("information", 0),
                    },
                    "support": {
                        "is_support": False,
                        "parent_id": None,
                        "parent_title": None,
                        "children_count": 0,
                    },
                    "ui": {
                        "show_type_switch": True,
                        "show_district": True,
                        "resources_editable": True,
                    },
                }

            # ---- ветвление по типу действия ----
            kind = (action_ctx["kind"] or "").lower()

            # по умолчанию (defend/attack) — как было
            resources_for_kb = ["force", "money", "influence", "information"]
            keyboard: KeyboardSpec
            action_ctx["join_link"] = make_support_link(config.bot_name, action_obj.id) \
                if action_obj.type == ActionType.COLLECTIVE and action_obj.status == ActionStatus.PENDING \
                else None
            if kind in ("defend", "attack"):
                action_ctx["ui"]["show_type_switch"] = True
                action_ctx["ui"]["show_district"] = True
                action_ctx["ui"]["resources_editable"] = True
                is_help = action_ctx.get("type").lower() == "support"
                keyboard = action_setup_kb(resources_for_kb, action_ctx["id"], action_ctx["status"], is_help=is_help)

            elif kind == "scout":
                # скрываем переключатель типа, район и редактирование ресурсов
                action_ctx["ui"]["show_type_switch"] = False
                action_ctx["ui"]["show_district"] = False
                action_ctx["ui"]["resources_editable"] = False

                # минимальная клавиатура: Done/Back
                button_params = {"done": {"action_id": action_ctx["id"]}, "delete": {"action_id": action_ctx["id"]}}
                opts = [["delete", "done"], ["back"]] if action_obj.status is ActionStatus.DRAFT else [["back"]]
                keyboard = KeyboardSpec(
                    type="inline",
                    name="action_setup_menu",
                    options=opts,
                    params=KeyboardParams(max_in_row=1),
                    button_params=button_params,
                )

            elif kind == "communicate":
                # район не настраивается; тратится только информация
                action_ctx["ui"]["show_type_switch"] = False      # без инд/коллектива
                action_ctx["ui"]["show_district"] = False         # скрываем район
                action_ctx["ui"]["resources_editable"] = True     # редактируем только information

                resources_for_kb = ["information"]
                keyboard = action_setup_kb(resources_for_kb, action_ctx["id"], action_ctx["status"], communicate=True)

            else:
                # запасной вариант — поведение как у defend
                keyboard = action_setup_kb(resources_for_kb, action_ctx["id"], action_ctx["status"])

        logging.info("Jinja ctx keys for %s: %s", self.__class__.__name__, action_ctx)

        return {
            "action": action_ctx,
            "keyboard": keyboard,
        }
