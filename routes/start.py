from aiogram.filters import Command

from screens.main_menu import MainMenuScreen

import logging
from aiogram import types, Router
from aiogram.filters import CommandStart, CommandObject
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, Action, ActionType, ActionStatus
from screens.registration_screen import RegistrationScreen, RegistrationSuccessScreen
from screens.settings_action import SettingsActionScreen

router = Router()


@router.message(CommandStart(deep_link=True))
async def start_with_payload(message: types.Message, command: CommandObject, state):
    payload = (command.args or "").strip()
    logging.info("Handling /start payload=%r from user_id=%s", payload, message.from_user.id)

    # Нет payload — обычный /start
    if not payload:
        logging.info("Handling /start from user_id=%s", message.from_user.id)

        # на всякий очищаем предыдущие состояния
        try:
            await state.clear()
        except Exception:
            pass
        await MainMenuScreen().run(message=message, actor=message.from_user, state=state, force_new=True)

    # Поддержка формата support_<ID>
    if not payload.startswith("support_"):
        await message.answer("Некорректная ссылка. Параметр не распознан.")
        return

    # --- Разбираем parent_id ---
    try:
        parent_id = int(payload.split("_", 1)[1])
    except Exception:
        await message.answer("Некорректный идентификатор действия в ссылке.")
        return

    async with get_session() as session:
        # 1) ensure user
        user = await User.get_by_tg_id(session, message.from_user.id)
        if not user:
            user = await User.create(
                session=session,
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                language_code=message.from_user.language_code,
            )

        # 2) load parent action
        parent: Action | None = (
            await session.execute(
                select(Action)
                .options(
                    selectinload(Action.owner),
                    selectinload(Action.district),
                )
                .where(Action.id == parent_id)
            )
        ).scalars().first()

        if not parent:
            await message.answer("Исходная заявка не найдена.")
            return

        # 🚫 запрет присоединения к своей заявке
        if parent.owner_id == user.id:
            await message.answer(
                "Нельзя присоединиться к своей же заявке (атака/оборона). "
                "Поддержка доступна только для действий других игроков."
            )
            return

        # 3) валидации: только defend/attack и только PENDING
        parent_kind = (parent.kind or "").lower()
        if parent_kind not in ("defend", "attack"):
            await message.answer("Присоединиться можно только к защите или атаке.")
            return

        if parent.status != ActionStatus.PENDING:
            await message.answer("Нельзя присоединиться: исходная заявка не в статусе PENDING.")
            return

        # 4) создаём support-заявку (kind наследуем, тип = SUPPORT, район копируем)
        child = await Action.create(
            session,
            owner_id=user.id,
            kind=parent.kind,  # наследуем kind (defend/attack)
            title=f"Поддержка #{parent.id}",
            district_id=parent.district_id,  # копируем район
            type=ActionType.SUPPORT,  # тип — support
            parent_action_id=parent.id,  # связываем с родителем
            status=ActionStatus.DRAFT,  # даём игроку настроить ресурсы
            force=0, money=0, influence=0, information=0,
        )

    # 5) открываем экран настройки новой заявки
    await SettingsActionScreen().run(
        message=message,
        actor=message.from_user,
        state=state,
        action_id=child.id,
        force_new=True
    )


@router.message(CommandStart())
@router.message(Command("start"))
async def start_handler(message: types.Message, state):
    logging.info("Handling /start from user_id=%s", message.from_user.id)

    # на всякий очищаем предыдущие состояния
    try:
        await state.clear()
    except Exception:
        pass
    await MainMenuScreen().run(message=message, actor=message.from_user, state=state, force_new=True)
