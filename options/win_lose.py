import logging

from aiogram.fsm.context import FSMContext
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload
from aiogram import types
from db.session import get_session
from db.models import Action, ActionStatus, District, User
from options.registry import option
from services.notify import notify_user
from utils.get_last_cycle_finished import read_last_cycle_finished


from datetime import datetime, timezone

def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    # если дата без tz — считаем, что это уже UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

@option("winlose_menu_i_won")
async def winlose_menu_i_won(cb: types.CallbackQuery, state: FSMContext, **kwargs):
    action_id = kwargs.get("action_id")
    if not action_id:
        await cb.answer("Нет action_id.", show_alert=True)
        return

    async with get_session() as session:
        action = (await session.execute(
            select(Action).where(Action.id == int(action_id))
        )).scalars().first()

        if not action:
            await cb.answer("Заявка не найдена.", show_alert=True)
            return

        action.won_on_point = True
        await session.commit()

        # попробуем сразу дорешать спор, если все ответили
        await _try_resolve_personal_duel(session, cb, action)

    await cb.answer("Отметка «Я победил» сохранена ✅")


@option("winlose_menu_i_lost")
async def winlose_menu_i_lost(cb: types.CallbackQuery, state: FSMContext, **kwargs):
    action_id = kwargs.get("action_id")
    if not action_id:
        await cb.answer("Нет action_id.", show_alert=True)
        return

    async with get_session() as session:
        action = (await session.execute(
            select(Action).where(Action.id == int(action_id))
        )).scalars().first()

        if not action:
            await cb.answer("Заявка не найдена.", show_alert=True)
            return

        action.won_on_point = False
        await session.commit()

        # попробуем сразу дорешать спор, если все ответили
        await _try_resolve_personal_duel(session, cb, action)

    await cb.answer("Отметка «Я проиграл» сохранена ✅")


async def _try_resolve_personal_duel(session, cb: types.CallbackQuery, trigger_action: Action) -> None:
    """
    1) Берёт datetime последнего цикла (read_last_cycle_finished()).
    2) Собирает все pending on_point-экшены по району trigger_action.
    3) Если у всех выставлен won_on_point:
       - Если ровно один True → район у победителя, прочие заявки по этому району
         (созданные ДО таймстемпа последнего цикла) переводим в DONE, всем уведомление.
       - Иначе → шлём админам подсказки-команды.
    """
    if not trigger_action.district_id:
        return

    cutoff = read_last_cycle_finished()
    if cutoff is None:
        cutoff = datetime.now(timezone.utc)
    else:
        cutoff = _as_utc(cutoff)

    # moving_on_point поддержим как алиас к on_point
    ONP = getattr(Action, "moving_on_point", Action.on_point)

    # Все pending on-point действия по этому району (и атаки, и защиты)
    q = (
        select(Action)
        .options(selectinload(Action.owner))
        .where(
            Action.status == ActionStatus.PENDING,
            Action.district_id == trigger_action.district_id,
            ONP.is_(True),
        )
        .order_by(Action.created_at.asc(), Action.id.asc())
    )
    actions = list((await session.execute(q)).scalars().all())

    if not actions:
        return

    # Проверяем: все ли ответили
    if any(a.won_on_point is None for a in actions):
        return  # ждём, пока все участники этого района ответят

    # Ровно один победитель?
    winners = [a for a in actions if a.won_on_point is True]
    district = await District.get_by_id(session, trigger_action.district_id)
    district_name = district.name if district else f"#{trigger_action.district_id}"

    # Бот для нотификаций (если есть)
    try:
        bot = cb.bot
    except Exception:
        bot = None

    if len(winners) == 1:
        winner = winners[0]
        # 1) Поменять владельца района
        if district:
            await District.reassign_owner(session, district_id=district.id, new_owner_id=winner.owner_id)

        # 2) Закрыть прочие заявки ДО таймстемпа последнего цикла (и самого победителя тоже логично закрыть)
        to_close_ids: list[int] = []
        for a in actions:
            ca = _as_utc(a.created_at)
            if ca and ca <= cutoff:
                to_close_ids.append(a.id)
        if to_close_ids:
            await session.execute(
                update(Action)
                .where(Action.id.in_(to_close_ids))
                .values(status=ActionStatus.DONE)
            )

        await session.commit()

        # 3) Нотификации всем участникам
        if bot:
            user_ids = {a.owner_id for a in actions}
            uq = await session.execute(select(User).where(User.id.in_(user_ids)))
            users_map = {u.id: u for u in uq.scalars().all()}
            winner_user = users_map.get(winner.owner_id)
            winner_name = (winner_user.in_game_name or winner_user.username or f"User#{winner_user.id}") if winner_user else "неизвестно"

            text = f'В личном бою в районе «{district_name}» победил {winner_name}.'
            for uid in user_ids:
                u = users_map.get(uid)
                if not u:
                    continue
                try:
                    await notify_user(bot, u.tg_id, title="⚔️ Итог личного боя", body=text)
                except Exception:
                    logging.exception("Не удалось отправить уведомление участнику личного боя (user_id=%s)", uid)

        return

    # Иначе (нет победителя или несколько победителей) — оповещаем админов
    admin_q = await session.execute(select(User).where(User.is_admin.is_(True)))
    admins = list(admin_q.scalars().all())

    if not admins or not bot:
        return

    # Подготовим строки-подсказки
    # Для каждого участника: `/set_district_owner #<district_id> @<username>` -- <won_on_point>
    lines = []
    for a in actions:
        u = a.owner  # подгружен selectinload'ом
        uname = (u.username or f"user{u.id}") if u else f"user{a.owner_id}"
        mark = "won=True" if a.won_on_point is True else ("won=False" if a.won_on_point is False else "won=None")
        lines.append(f"/set_district_owner #{trigger_action.district_id} @{uname} -- {mark}")

    body = "Спорный район {} не разрешился:\n{}".format(district_name, "\n".join(lines))

    for admin in admins:
        try:
            await notify_user(bot, admin.tg_id, title="⚖️ Требуется ручное решение", body=body)
        except Exception:
            logging.exception("Не удалось отправить уведомление администратору (user_id=%s)", admin.id)
