# text_inputs/scout_info.py  (или где у тебя лежат текстовые хэндлеры)
import logging
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from states.scout import Scout

from db.session import get_session
from db.models import User, Action, ActionStatus, ActionType
from screens.settings_action import SettingsActionScreen
from screens.scout_info_screen import ScoutInfoScreen
from text_handlers import text_handler


@text_handler(Scout.waiting_question)
async def handle_scout_info_question(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        if not raw:
            raise ValueError("Пустая строка. Напишите ваш вопрос (1..600 символов).")
        if len(raw) > 600:
            raise ValueError("Слишком длинно. Максимум 600 символов.")

        tg_id = message.from_user.id
        async with get_session() as session:
            # 1) Пользователь
            user = await User.get_by_tg_id(session, tg_id)
            if not user:
                user = await User.create(
                    session=session,
                    tg_id=tg_id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    language_code=message.from_user.language_code,
                )

            # 2) Создаём DRAFT-заявку SCOUT (вопрос мастерам)
            #    — без района
            #    — тип оставим INDIVIDUAL
            #    — списание ресурсов произойдёт позже при "Done"
            action = await Action.create(
                session,
                owner_id=user.id,
                kind="scout",
                title="Вопрос мастерской группе",
                district_id=None,
                type=ActionType.INDIVIDUAL,
                status=ActionStatus.DRAFT,
                force=0,
                money=0,
                influence=0,
                information=1,  # стоимость будет проверяться и списываться при отправке (Done)
            )

            # Добавим текст вопроса в поле action.text (если оно уже добавлено в модель)
            # Если у тебя нет метода update, можно напрямую присвоить и commit
            action.text = raw
            await session.commit()
            await session.refresh(action)

        # показываем экран настроек конкретной заявки
        await SettingsActionScreen().run(
            message=message,
            actor=message.from_user,
            state=state,
            action_id=action.id,
            force_new=True
        )

    except Exception as e:
        logging.exception("Scout question creation failed")
        # Покажем экран снова с ошибкой и заново поставим ожидание текста
        await ScoutInfoScreen().run(
            message=message,
            actor=message.from_user,
            state=state,
            error_text=str(e) or "Неизвестная ошибка. Попробуйте ещё раз.",
            force_new=True
        )
