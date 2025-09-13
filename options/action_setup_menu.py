# options/action_setup.py
import asyncio
import logging
from typing import Optional, List

from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from utils.ask_and_answer import append_ask_and_answer
from utils.news_to_print import add_news_to_print
from utils.rituals import append_ritual
from .registry import option
from db.session import get_session
from db.models import Action, ActionType, User, ActionStatus, District
from screens.settings_action import SettingsActionScreen

from utils.raw_body_input import add_raw_row

# --- NOTIFY HELPERS -----------------------------------------------------------
from services.notify import notify_user  # <- как мы делали ранее

_MAX_CANDLES = 8


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
    if (action.kind or "").lower() not in ("defend", "attack", "ritual"):
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
    title = f"🔔 Действие на районе {action.district.name}"

    extra = "\nЛично присутствует на районе." if getattr(action, "on_point", False) else ""

    if not (action.kind or "").lower() == "ritual":
        body = (
            f"{who} начал(а) «{(action.kind or '').capitalize()}»"
            f"{f' — {action.title}' if action.title else ''}.\n"
            f"Оценка ресурсов: около {estimate}{extra}"
        )
        for w in watchers:
            await notify_user(bot, w.tg_id, title=title, body=body)
    else:
        body = (
            f"{who} начал(а) Ритуал в этом районе!"
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


@option("action_setup_menu_increase")
async def action_setup_menu_is_positive_increase(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    """
    Устанавливает флаг is_positive=True для действия.
    """
    try:
        async with get_session() as session:
            user = (await session.execute(select(User).where(User.tg_id == cb.from_user.id))).scalars().first()
            action = (await session.execute(select(Action).where(Action.id == action_id))).scalars().first()

            if not user or not action:
                await cb.answer("Не найдена заявка/пользователь.", show_alert=True)
                return
            if action.owner_id != user.id:
                await cb.answer("Эта заявка принадлежит другому игроку.", show_alert=True)
                return
            if action.status in (ActionStatus.DONE, ActionStatus.FAILED, ActionStatus.DELETED):
                await cb.answer("Действие уже зафиксировано и не может быть изменено.", show_alert=True)
                return

            if action.is_positive is True:
                await cb.answer("Уже отмечено как позитивное ✅")
                return

            action.is_positive = True
            await session.commit()

        await _rerender(cb, state, action_id)
        await cb.answer("Позиция отмечена как позитивная ✅")

    except Exception:
        logging.exception("action_setup_menu_is_positive_increase failed")
        await cb.answer("Ошибка при изменении флага.", show_alert=True)


@option("action_setup_menu_decrease")
async def action_setup_menu_is_positive_decrease(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    """
    Устанавливает флаг is_positive=False для действия.
    """
    try:
        async with get_session() as session:
            user = (await session.execute(select(User).where(User.tg_id == cb.from_user.id))).scalars().first()
            action = (await session.execute(select(Action).where(Action.id == action_id))).scalars().first()

            if not user or not action:
                await cb.answer("Не найдена заявка/пользователь.", show_alert=True)
                return
            if action.owner_id != user.id:
                await cb.answer("Эта заявка принадлежит другому игроку.", show_alert=True)
                return
            if action.status in (ActionStatus.DONE, ActionStatus.FAILED, ActionStatus.DELETED):
                await cb.answer("Действие уже зафиксировано и не может быть изменено.", show_alert=True)
                return

            if action.is_positive is False:
                await cb.answer("Уже отмечено как негативное ⛔")
                return

            action.is_positive = False
            await session.commit()

        await _rerender(cb, state, action_id)
        await cb.answer("Позиция отмечена как негативная ⛔")

    except Exception:
        logging.exception("action_setup_menu_is_positive_decrease failed")
        await cb.answer("Ошибка при изменении флага.", show_alert=True)


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


async def _bump_candles(cb: types.CallbackQuery, state: FSMContext, action_id: int, delta: int):
    async with get_session() as session:
        user = (await session.execute(select(User).where(User.tg_id == cb.from_user.id))).scalars().first()
        action = (await session.execute(select(Action).where(Action.id == action_id))).scalars().first()

        if not user or not action:
            await cb.answer("Не найдена заявка/пользователь.", show_alert=True)
            return
        if action.owner_id != user.id:
            await cb.answer("Эта заявка принадлежит другому игроку.", show_alert=True)
            return

        current = int(action.candles or 0)
        new_val = max(0, min(_MAX_CANDLES, current + delta))  # держим 0..8 при редактировании

        if new_val == current:
            if delta > 0 and current >= _MAX_CANDLES:
                await cb.answer("Максимум 8 свечей.")
            elif delta < 0 and current <= 0:
                await cb.answer("И так уже 0.")
            else:
                await cb.answer("Без изменений.")
            return

        action.candles = new_val
        await session.commit()

    await _rerender(cb, state, action_id)
    await cb.answer(f"{'➕' if delta > 0 else '➖'} candles: {current} → {new_val}")


@option("action_setup_menu_candles_add")
async def action_setup_menu_candles_add(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_candles(cb, state, action_id, +1)


@option("action_setup_menu_candles_remove")
async def action_setup_menu_candles_remove(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    await _bump_candles(cb, state, action_id, -1)


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

            # 🔍 Анти-дубликат только для заявок, привязанных к району
            if action.district_id is not None:
                # parent_action_id: корректно сравниваем NULL/NOT NULL
                parent_cond = (
                    Action.parent_action_id.is_(None)
                    if action.parent_action_id is None
                    else Action.parent_action_id == action.parent_action_id
                )
                dup_q = (
                    select(Action.id)
                    .where(
                        Action.kind == action.kind,
                        Action.status == ActionStatus.PENDING,
                        Action.owner_id == user.id,
                        Action.district_id == action.district_id,
                        parent_cond,
                        Action.id != action.id,  # исключаем саму заявку
                    )
                    .limit(1)
                )
                dup_exists = (await session.execute(dup_q)).scalar() is not None
                if dup_exists:
                    await cb.answer(
                        "Такая же заявка уже создана и ожидает обработки. "
                        "Отредактируй существующую.",
                        show_alert=True,
                    )
                    return

            is_ritual = (action.kind or "").lower() == "ritual"
            if is_ritual:
                cnt = int(action.candles or 0)
                if cnt < 1 or cnt > _MAX_CANDLES:
                    await cb.answer("Укажи число свечей от 1 до 8.", show_alert=True)
                    return
            else:
                total_resources = (action.money or 0) + (action.influence or 0) + (action.information or 0) + (
                        action.force or 0)
                if total_resources <= 0 and not getattr(action, "on_point", False):
                    await cb.answer("Заявка пуста: добавьте ресурсы или включите флаг 'Едем на точку'.",
                                    show_alert=True)
                    return

            if (user.available_actions or 0) <= 0:
                await cb.answer("Недостаточно слотов действий.", show_alert=True)
                return

            if is_ritual:
                need_money = need_infl = need_info = need_force = 0
            else:
                need_money = action.money or 0
                need_infl = action.influence or 0
                need_info = action.information or 0
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

            # списание ресурсов и слота (для ритуала ресурсы = 0 → ничего не снимется)
            user.money -= need_money
            user.influence -= need_infl
            user.information -= need_info
            user.force -= need_force
            user.available_actions = max(0, (user.available_actions or 0) - 1)

            action.status = ActionStatus.PENDING

            # 🔹 если это разведка района — добавить район в список разведок пользователя
            if action.type == ActionType.SCOUT_DISTRICT and action.district_id:
                await session.refresh(user, attribute_names=["scouts_districts"])
                already = any(d.id == action.district_id for d in (user.scouts_districts or []))
                if not already:
                    district = await session.get(District, action.district_id)
                    if district is not None:
                        user.scouts_districts.append(district)

            await session.commit()
            try:
                is_ritual = (action.kind or "").lower() == "ritual"
                if is_ritual:
                    u_name = (user.in_game_name or user.username or f"tg:{user.tg_id}").strip()
                    a_text = (action.text or "").strip()
                    candles = int(action.candles or 0)

                    raw_body = f"\"{u_name}\" начал ритуал: \"{a_text}\" на \"{candles}\" свечей"
                    # не заполняем title / created_at / to_send — только raw_body и type
                    await asyncio.to_thread(add_raw_row, raw_body=raw_body, created_at=str(action.created_at),
                                            type_value="ritual.start")
                    await asyncio.to_thread(append_ritual,
                                            action_title=action.title,
                                            action_user_in_game_name=u_name,
                                            action_text=action.text,
                                            created_at=action.created_at,
                                            action_id=action.id
                                            )
            except Exception:
                logging.exception("failed to append ritual RAW news")
            try:
                # Для разведки НЕ по району: отправляем вопрос в ask_and_answer
                is_scout_kind = (action.kind or "").lower().startswith("scout")
                if is_scout_kind and action.type != ActionType.SCOUT_DISTRICT:
                    await asyncio.to_thread(
                        append_ask_and_answer,
                        username=(user.username or "").strip(),
                        in_game_name=(user.in_game_name or "").strip(),
                        question=(action.text or "").strip(),
                        action_id=action.id,
                    )
            except Exception:
                logging.exception("failed to append ask_and_answer for scout")
            try:
                is_communicate = (action.kind or "").lower() == "communicate"
                if is_communicate:
                    title = (action.title or "Предложение новости").strip()
                    body = (action.text or "").strip()
                    # отправляем сразу в конвейер (to_send=True)
                    await asyncio.to_thread(
                        add_news_to_print,
                        title=title,
                        body=body,
                        action_id=action.id,
                        spent_info=(action.information or 0),
                        to_send=False,  # отметим для переноса в news
                        # created_at=None      # оставим по умолчанию — функция проставит текущее время
                    )
            except Exception:
                logging.exception("failed to append communicate news_to_print")
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


@option("action_setup_menu_moving_on_point")
async def action_setup_menu_moving_on_point(cb: types.CallbackQuery, state: FSMContext, action_id: int, **_):
    """
    Инвертирует флаг on_point у Action(id=action_id).
    Ничего не перерисовывает и не меняет в UI.
    """
    try:
        async with get_session() as session:
            user = (await session.execute(
                select(User).where(User.tg_id == cb.from_user.id)
            )).scalars().first()
            action = (await session.execute(
                select(Action).where(Action.id == action_id)
            )).scalars().first()

            if not user or not action:
                await cb.answer("Не найдена заявка/пользователь.", show_alert=True)
                return
            if action.owner_id != user.id:
                await cb.answer("Эта заявка принадлежит другому игроку.", show_alert=True)
                return
            if action.status in (ActionStatus.DONE, ActionStatus.FAILED, ActionStatus.DELETED):
                await cb.answer("Действие уже зафиксировано и не может быть изменено.", show_alert=True)
                return

            new_value = not bool(action.on_point)
            action.on_point = new_value
            await session.commit()

        await cb.answer("Маркер «on point» включён ✅" if new_value else "Маркер «on point» выключен ⛔")

    except Exception:
        logging.exception("action_setup_menu_moving_on_point failed")
        await cb.answer("Ошибка при изменении флага.", show_alert=True)
