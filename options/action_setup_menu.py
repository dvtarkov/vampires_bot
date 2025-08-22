# options/action_setup.py
import logging
from typing import Optional, List

from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload


from .registry import option
from db.session import get_session
from db.models import Action, ActionType, User, ActionStatus, District
from screens.settings_action import SettingsActionScreen


# --- NOTIFY HELPERS -----------------------------------------------------------
from services.notify import notify_user  # <- как мы делали ранее

def _fmt_resources(action: Action) -> str:
    parts = []
    if (action.force or 0) > 0:       parts.append(f"💪 сила: {action.force}")
    if (action.money or 0) > 0:       parts.append(f"💰 деньги: {action.money}")
    if (action.influence or 0) > 0:   parts.append(f"🪙 влияние: {action.influence}")
    if (action.information or 0) > 0: parts.append(f"🧠 информация: {action.information}")
    if getattr(action, "on_point", False):
        parts.append("📍 на точке")
    return ", ".join(parts) if parts else "ресурсы не указаны"

async def _iter_district_watchers(session, district_id: int, exclude_user_id: int):
    """
    Возвращает генератор пользователей, которые наблюдают (scout) за районом,
    исключая инициатора.
    """
    district = await session.get(District, district_id)
    if not district:
        return []
    # подгрузим связь
    await session.refresh(district, attribute_names=["scouting_by"])
    return [u for u in (district.scouting_by or []) if u.id != exclude_user_id]


async def _notify_watchers_action_started(session, bot, actor: User, action: Action):
    """
    Шлём наблюдателям района уведомление о том, что началось действие на районе.
    Только для defend/attack с указанным районом и статусом PENDING.
    """

    if not action.district_id:
        return
    if (action.kind or "").lower() not in ("defend", "attack"):
        return
    if action.status != ActionStatus.PENDING:
        return

    watchers = await _iter_district_watchers(session, action.district_id, exclude_user_id=actor.id)

    if not watchers:
        return

    total = (
                    (action.money or 0)
                    + (action.influence or 0)
                    + (action.information or 0)
                    + (action.force or 0)
            ) * 5
    estimate = round(total, -1)

    who = actor.in_game_name or actor.username or f"#{actor.tg_id}"
    title = "🔔 Действие на районе"

    extra = "\nПротивник атакует район лично." if getattr(action, "on_point", False) else ""

    body = (
        f"{who} начал(а) «{(action.kind or '').capitalize()}»"
        f"{f' — {action.title}' if action.title else ''}.\n"
        f"Оценка ресурсов: около {estimate}{extra}"
    )
    for w in watchers:
        await notify_user(bot, w.tg_id, title=title, body=body)

async def _notify_watchers_action_cancelled(session, bot, actor: User, action: Action, reason: str = "отменено"):
    """
    Шлём наблюдателям уведомление, что действие отменено/возвращено в черновик/удалено.
    Только если было связано с районом и это defend/attack.
    """
    if not action.district_id:
        return
    if (action.kind or "").lower() not in ("defend", "attack"):
        return

    watchers = await _iter_district_watchers(session, action.district_id, exclude_user_id=actor.id)
    if not watchers:
        return

    who = actor.in_game_name or actor.username or f"#{actor.tg_id}"
    title = "🔔 Действие отменено"
    body = (
        f"{who} {reason} действие «{(action.kind or '').capitalize()}»"
        f"{f' — {action.title}' if action.title else ''}."
    )
    for w in watchers:
        await notify_user(bot, w.tg_id, title=title, body=body)
# -------------------------------------------------------------------------------


async def _rerender(cb: types.CallbackQuery, state: FSMContext, action_id: int):
    # пусть экран сам достанет action по id, чтобы не таскать «живой» ORM-объект между сессиями
    await SettingsActionScreen().run(
        message=cb.message, actor=cb.from_user, state=state,
        action_id=action_id
    )


@option("action_setup_menu_collective")
async def action_setup_menu_collective(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.tg_id == cb.from_user.id))).scalars().first()
        action = (await session.execute(select(Action).where(Action.id == action_id))).scalars().first()

        if not user or not action:
            await cb.answer("Не найдена заявка/пользователь.", show_alert=True)
            return

        if action.type == ActionType.COLLECTIVE:
            await cb.answer("Заявка уже коллективная.")
            return

        action.type = ActionType.COLLECTIVE
        await session.commit()

    await _rerender(cb, state, action_id)
    await cb.answer("Тип изменён на коллективный ✅")


@option("action_setup_menu_individual")
async def action_setup_menu_individual(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.tg_id == cb.from_user.id))).scalars().first()
        action = (await session.execute(select(Action).where(Action.id == action_id))).scalars().first()

        if not user or not action:
            await cb.answer("Не найдена заявка/пользователь.", show_alert=True)
            return

        if action.type == ActionType.INDIVIDUAL:
            await cb.answer("Заявка уже индивидуальная.")
            return

        action.type = ActionType.INDIVIDUAL
        await session.commit()

    await _rerender(cb, state, action_id)
    await cb.answer("Тип изменён на индивидуальный ✅")


_RESOURCE_FIELDS = {"force", "money", "influence", "information"}
_STEP = 1


async def _bump_resource(cb: types.CallbackQuery, state: FSMContext, action_id: int, field: str, delta: int):
    if field not in _RESOURCE_FIELDS:
        await cb.answer("Неизвестный ресурс.", show_alert=True)
        return

    async with get_session() as session:
        user = (await session.execute(select(User).where(User.tg_id == cb.from_user.id))).scalars().first()
        action = (await session.execute(select(Action).where(Action.id == action_id))).scalars().first()
        if not user or not action:
            await cb.answer("Не найдена заявка/пользователь.", show_alert=True)
            return

        current = getattr(action, field, 0) or 0
        cap = getattr(user, field, 0) or 0

        new_val = current + delta
        if new_val < 0:
            new_val = 0
        if new_val > cap:
            new_val = cap

        if new_val == current:
            if delta > 0 and current >= cap:
                await cb.answer("Больше вложить нельзя — нет свободных ресурсов.")
            elif delta < 0 and current <= 0:
                await cb.answer("И так уже 0.")
            else:
                await cb.answer("Без изменений.")
            return

        setattr(action, field, new_val)
        await session.commit()

    await _rerender(cb, state, action_id)
    sign = "➕" if delta > 0 else "➖"
    await cb.answer(f"{sign} {field}: {current} → {new_val}")


@option("action_setup_menu_money_add")
async def action_setup_menu_money_add(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "money", +_STEP)


@option("action_setup_menu_money_remove")
async def action_setup_menu_money_remove(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "money", -_STEP)


@option("action_setup_menu_influence_add")
async def action_setup_menu_influence_add(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "influence", +_STEP)


@option("action_setup_menu_influence_remove")
async def action_setup_menu_influence_remove(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "influence", -_STEP)


@option("action_setup_menu_information_add")
async def action_setup_menu_information_add(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "information", +_STEP)


@option("action_setup_menu_information_remove")
async def action_setup_menu_information_remove(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "information", -_STEP)


@option("action_setup_menu_force_add")
async def action_setup_menu_force_add(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "force", +_STEP)


@option("action_setup_menu_force_remove")
async def action_setup_menu_force_remove(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_resource(cb, state, action_id, "force", -_STEP)


@option("action_setup_menu_back")
async def action_setup_menu_back(cb: types.CallbackQuery, state: FSMContext, **kwargs):
    from screens.actions import ActionsScreen
    from screens.actions_stats import ActionsStatsScreen
    is_list = kwargs.get("is_list")
    if is_list:
        await ActionsStatsScreen().run(message=cb.message, actor=cb.from_user, state=state)
        await cb.answer()
    else:
        await ActionsScreen().run(message=cb.message, actor=cb.from_user, state=state)
    await cb.answer()


@option("action_setup_menu_done")
async def action_setup_menu_done(cb: types.CallbackQuery, state, action_id: int, **_):
    try:
        async with get_session() as session:
            user = await User.get_by_tg_id(session, cb.from_user.id)
            if not user:
                await cb.answer("Пользователь не найден.", show_alert=True)
                return

            action = (await session.execute(
                select(Action)
                .options(selectinload(Action.owner))
                .where(Action.id == action_id)
            )).scalars().first()

            if not action:
                await cb.answer("Заявка не найдена.", show_alert=True)
                return
            if action.owner_id != user.id:
                await cb.answer("Эта заявка принадлежит другому игроку.", show_alert=True)
                return
            if action.status not in (ActionStatus.PENDING, ActionStatus.DRAFT):
                await cb.answer(f"Нельзя отправить заявку в статусе: {action.status.value}.", show_alert=True)
                return

            total_resources = (action.money or 0) + (action.influence or 0) + (action.information or 0) + (action.force or 0)
            if total_resources <= 0 and not getattr(action, "on_point", False):
                await cb.answer("Заявка пуста: добавьте ресурсы или включите флаг 'Едем на точку'.", show_alert=True)
                return

            if (user.available_actions or 0) <= 0:
                await cb.answer("Недостаточно слотов действий.", show_alert=True)
                return

            need_money = action.money or 0
            need_infl  = action.influence or 0
            need_info  = action.information or 0
            need_force = action.force or 0

            lack = []
            if user.money < need_money:
                lack.append(f"💰 не хватает {need_money - user.money}")
            if user.influence < need_infl:
                lack.append(f"🪙 не хватает {need_infl - user.influence}")
            if user.information < need_info:
                lack.append(f"🧠 не хватает {need_info - user.information}")
            if user.force < need_force:
                lack.append(f"💪 не хватает {need_force - user.force}")
            if lack:
                await cb.answer("Недостаточно ресурсов: " + ", ".join(lack), show_alert=True)
                return

            # списание ресурсов и слота
            user.money       -= need_money
            user.influence   -= need_infl
            user.information -= need_info
            user.force       -= need_force
            user.available_actions = max(0, (user.available_actions or 0) - 1)

            # переводим в PENDING
            action.status = ActionStatus.PENDING

            # 🔹 если это разведка района — добавить район в список разведок пользователя
            if action.type == ActionType.SCOUT_DISTRICT and action.district_id:
                # подгрузим текущие связи, чтобы не дублировать
                await session.refresh(user, attribute_names=["scouts_districts"])
                already = any(d.id == action.district_id for d in (user.scouts_districts or []))
                if not already:
                    district = await session.get(District, action.district_id)
                    if district is not None:
                        user.scouts_districts.append(district)

            await session.commit()
            try:
                logging.info("notify watchers started")
                await _notify_watchers_action_started(session, cb.bot, user, action)
            except Exception:
                logging.exception("notify watchers (start) failed")
        await cb.answer("Заявка отправлена и будет обработана в конце цикла.", show_alert=False)

        await SettingsActionScreen().run(
            message=cb.message,
            actor=cb.from_user,
            state=state,
            action_id=action_id
        )

    except Exception as e:
        logging.exception("action_setup_menu_done failed")
        await cb.answer(f"Ошибка: {e}", show_alert=True)


def _cap_actions(user: User, inc: int = 1) -> None:
    """Вернёт +inc слотов, не превышая max_available_actions (если задан)."""
    cur = (user.available_actions or 0) + inc
    mx = user.max_available_actions
    if mx is not None:
        cur = min(cur, mx)
    user.available_actions = max(0, cur)


@option("action_setup_menu_edit")
async def action_setup_menu_edit(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    """
    Перевод в DRAFT. Если был PENDING, вернуть ресурсы игроку и слот действия.
    Ресурсы в заявке НЕ обнуляем.
    """
    try:
        async with get_session() as session:
            user = await User.get_by_tg_id(session, cb.from_user.id)
            if not user:
                await cb.answer("Пользователь не найден.", show_alert=True)
                return

            action = (await session.execute(
                select(Action)
                .options(selectinload(Action.owner))
                .where(Action.id == action_id)
            )).scalars().first()

            if not action:
                await cb.answer("Заявка не найдена.", show_alert=True)
                return
            if action.owner_id != user.id:
                await cb.answer("Эта заявка принадлежит другому игроку.", show_alert=True)
                return
            if action.status == ActionStatus.DELETED:
                await cb.answer("Эта заявка уже удалена.", show_alert=True)
                return
            if action.status == ActionStatus.DRAFT:
                await cb.answer("Заявка уже в режиме редактирования (DRAFT).", show_alert=False)
            else:
                was_pending = (action.status == ActionStatus.PENDING)
                # Был PENDING (или иной активный статус) — вернуть ресурсы игроку и слот
                if was_pending:
                    user.money += (action.money or 0)
                    user.influence += (action.influence or 0)
                    user.information += (action.information or 0)
                    user.force += (action.force or 0)
                    _cap_actions(user, +1)

                # Перевести в DRAFT. Ресурсы в заявке оставляем как есть.
                action.status = ActionStatus.DRAFT
                await session.commit()

                # если отменяли PENDING — уведомим наблюдателей
                if was_pending and action.district_id and (action.kind or "").lower() in ("defend", "attack"):
                    try:
                        await _notify_watchers_action_cancelled(session, cb.bot, user, action,
                                                                reason="вернул(а) в черновик")
                    except Exception:
                        logging.exception("notify watchers (cancel/edit) failed")
                await cb.answer("Заявка переведена в DRAFT. Ресурсы и слот возвращены.", show_alert=False)

        await SettingsActionScreen().run(
            message=cb.message,
            actor=cb.from_user,
            state=state,
            action_id=action_id
        )

    except Exception as e:
        logging.exception("action_setup_menu_edit failed")
        await cb.answer(f"Ошибка: {e}", show_alert=True)


@option("action_setup_menu_delete")
async def action_setup_menu_delete(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    """
    Пометить заявку как DELETED.
    Если был PENDING — вернуть ресурсы игроку и слот действия.
    Ресурсы в самой заявке НЕ обнуляются.
    """
    try:
        async with get_session() as session:
            user = await User.get_by_tg_id(session, cb.from_user.id)
            if not user:
                await cb.answer("Пользователь не найден.", show_alert=True)
                return

            action = (await session.execute(
                select(Action)
                .options(selectinload(Action.owner))
                .where(Action.id == action_id)
            )).scalars().first()

            if not action:
                await cb.answer("Заявка не найдена.", show_alert=True)
                return
            if action.owner_id != user.id:
                await cb.answer("Эта заявка принадлежит другому игроку.", show_alert=True)
                return
            if action.status == ActionStatus.DELETED:
                await cb.answer("Заявка уже удалена.", show_alert=False)
            else:
                # Если была PENDING — рефанд ресурсов и слота
                was_pending = (action.status == ActionStatus.PENDING)

                if was_pending:
                    user.money += (action.money or 0)
                    user.influence += (action.influence or 0)
                    user.information += (action.information or 0)
                    user.force += (action.force or 0)
                    _cap_actions(user, +1)

                # Переводим в DELETED (ресурсы в заявке остаются как есть)
                action.status = ActionStatus.DELETED
                await session.commit()

                if was_pending and action.district_id and (action.kind or "").lower() in ("defend", "attack"):
                    try:
                        await _notify_watchers_action_cancelled(session, cb.bot, user, action, reason="удалил(а)")
                    except Exception:
                        logging.exception("notify watchers (cancel/delete) failed")

                await cb.answer("Заявка удалена. Ресурсы и слот возвращены (если были списаны).", show_alert=False)

        # Можно вернуть пользователя в список заявок или просто перерисовать экран.
        await SettingsActionScreen().run(
            message=cb.message,
            actor=cb.from_user,
            state=state,
            action_id=action_id
        )

    except Exception as e:
        logging.exception("action_setup_menu_delete failed")
        await cb.answer(f"Ошибка: {e}", show_alert=True)


# вспомогалка: перерисовка списка с навигацией и возможными статус-фильтрами
async def _rerender_list_nav(cb: types.CallbackQuery, state: FSMContext, move: str):
    statuses: Optional[List[str]] = None
    if state:
        try:
            data = await state.get_data()
            statuses = data.get("actions_list_statuses")  # опционально: если где-то сохраняешь фильтры
        except Exception:
            statuses = None

    await SettingsActionScreen().run(
        message=cb.message,
        actor=cb.from_user,
        state=state,
        is_list=True,
        move=move,
        statuses=statuses,
    )

@option("action_setup_menu_prev")
async def action_setup_menu_prev(cb: types.CallbackQuery, state: FSMContext, **_):
    try:
        await _rerender_list_nav(cb, state, move="prev")
        await cb.answer()
    except Exception as e:
        logging.exception("action_setup_menu_prev failed")
        await cb.answer(f"Ошибка: {e}", show_alert=True)

@option("action_setup_menu_next")
async def action_setup_menu_next(cb: types.CallbackQuery, state: FSMContext, **_):
    try:
        await _rerender_list_nav(cb, state, move="next")
        await cb.answer()
    except Exception as e:
        logging.exception("action_setup_menu_next failed")
        await cb.answer(f"Ошибка: {e}", show_alert=True)