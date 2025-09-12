from typing import Callable, Awaitable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from db.session import get_session
from db.models import User


def _norm_username(v: str | None) -> str | None:
    if not v:
        return None
    s = v.strip()
    if s.startswith("@"):
        s = s[1:]
    return s or None


class UserRegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        user_data = event.from_user
        username = _norm_username(user_data.username)

        async with get_session() as session:
            # 1) Есть запись с этим tg_id (>0)? — ок
            db_user = await User.get_by_tg_id(session, user_data.id)

            if not db_user:
                # 2) Если нет, а в базе есть «нулевая» запись с таким username (tg_id == 0),
                #    то «захватываем» её и проставляем реальный tg_id.
                placeholder = None
                if username:
                    placeholder = (
                        await session.execute(
                            select(User)
                            .where(
                                func.lower(User.username) == username.lower(),
                                User.tg_id == 0,
                            )
                        )
                    ).scalars().first()

                if placeholder:
                    placeholder.tg_id = user_data.id
                    # обновим заодно метаданные из Telegram (если есть)
                    placeholder.username = username
                    placeholder.first_name = user_data.first_name
                    placeholder.last_name = user_data.last_name
                    placeholder.language_code = user_data.language_code
                    await session.commit()
                else:
                    # 3) Иначе создаём нового пользователя с реальным tg_id
                    await User.create(
                        session=session,
                        tg_id=user_data.id,
                        username=username,
                        first_name=user_data.first_name,
                        last_name=user_data.last_name,
                        language_code=user_data.language_code,
                    )

        return await handler(event, data)
