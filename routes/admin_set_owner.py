# handlers/admin_set_owner.py
import re
import logging
from datetime import datetime, timezone
from typing import Optional, List

from aiogram import types, Router
from aiogram.filters import Command
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

from db.session import get_session
from db.models import User, District, Action, ActionStatus
from services.notify import notify_user
from utils.get_last_cycle_finished import read_last_cycle_finished

router = Router()
log = logging.getLogger(__name__)

ATTACK_KIND = "attack"
DEFENSE_KIND = "defend"


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_set_owner_args(text: str) -> tuple[Optional[int], Optional[str]]:
    """
    Ожидаем строку вида:
      /set_district_owner #1 @NotThatDroids
    Возвращаем (district_id, username_lc)
    """
    # снимем мусор и приведём к единому виду
    m = re.search(r"#\s*(\d+)", text)
    n = re.search(r"@([A-Za-z0-9_]{3,})", text)
    did = int(m.group(1)) if m else None
    uname = n.group(1).strip() if n else None
    if uname:
        uname = uname.lower()
    return did, uname


@router.message(Command("set_district_owner"))
async def set_district_owner_cmd(message: types.Message):
    """
    /set_district_owner #<district_id> @<username>
    """
    # 0) проверка прав
    async with get_session() as session:
        q = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        caller: User | None = q.scalars().first()

    if not caller or not getattr(caller, "is_admin", False):
        await message.answer("Недостаточно прав. Команда доступна только администраторам.")
        return

    # 1) парсинг аргументов
    did, uname = _parse_set_owner_args(message.text or "")
    if not did or not uname:
        await message.answer("Формат: /set_district_owner #<district_id> @<username>")
        return

    cutoff = read_last_cycle_finished()
    cutoff = _as_utc(cutoff) or datetime.now(timezone.utc)

    ONP = getattr(Action, "moving_on_point", Action.on_point)

    async with get_session() as session:
        # 2) пользователь-победитель
        uq = await session.execute(select(User).where(User.username.is_not(None)))
        winner_user: Optional[User] = None
        for u in uq.scalars().all():
            if (u.username or "").lower() == uname:
                winner_user = u
                break
        if not winner_user:
            await message.answer(f"Пользователь @{uname} не найден.")
            return

        # 3) район
        district = await District.get_by_id(session, did)
        if not district:
            await message.answer(f"Район #{did} не найден.")
            return

        # 4) pending on-point действия по району до cutoff
        q = (
            select(Action)
            .options(selectinload(Action.owner))
            .where(
                Action.status == ActionStatus.PENDING,
                Action.district_id == did,
                Action.kind.in_([ATTACK_KIND, DEFENSE_KIND]),
                ONP.is_(True),
                Action.created_at <= cutoff,
            )
            .order_by(Action.created_at.asc(), Action.id.asc())
        )
        actions: List[Action] = list((await session.execute(q)).scalars().all())
        if not actions:
            await message.answer("Нет подходящих on-point действий для указанного района.")
            return

        # 5) won_on_point
        winner_ids, loser_ids = [], []
        for a in actions:
            if a.owner_id == winner_user.id:
                a.won_on_point = True
                winner_ids.append(a.id)
            else:
                a.won_on_point = False
                loser_ids.append(a.id)

        # 6) передача района и закрытие заявок
        await District.reassign_owner(session, district_id=did, new_owner_id=winner_user.id)
        await session.execute(
            update(Action)
            .where(Action.id.in_([a.id for a in actions]))
            .values(status=ActionStatus.DONE)
        )
        await session.commit()

        # 7) нотификации участникам (если есть bot)
        try:
            from app import bot  # type: ignore
        except Exception:
            bot = None
            logging.warning("Бот недоступен: уведомления о ручном решении не отправлены.")

        if bot:
            owner_ids = {a.owner_id for a in actions}
            uq2 = await session.execute(select(User).where(User.id.in_(owner_ids)))
            users_map = {u.id: u for u in uq2.scalars().all()}
            district_name = district.name
            winner_name = (winner_user.in_game_name or winner_user.username or f"User#{winner_user.id}")
            text = f'Админом решён спор в районе «{district_name}»: победил {winner_name}. Район передан.'
            for uid in owner_ids:
                u = users_map.get(uid)
                if not u or not u.tg_id:
                    continue
                try:
                    await notify_user(bot, u.tg_id, title="⚔️ Итог личного боя (админ-решение)", body=text)
                except Exception:
                    logging.exception("Не удалось отправить уведомление участнику (user_id=%s)", uid)

    await message.answer(
        "Готово.\n"
        f"• Район: #{did} → «{district.name}»\n"
        f"• Победитель: @{winner_user.username or winner_user.id}\n"
        f"• Отмечено won_on_point: +{len(winner_ids)} / -{len(loser_ids)}\n"
        f"• Все on-point действия до {cutoff.isoformat()} закрыты как DONE."
    )
