# game_cycle.py
"""
Запуск:
    export DATABASE_URL="sqlite+aiosqlite:///./game.db"  # или ваша строка подключения
    export COMBAT_RATES_PATH="./config/combat_rates.json"
    python game_cycle.py

Что добавлено по сравнению с предыдущей версией:
- Аггрегация SUPPORT-экшенов в родительский (parent_action): все ресурсы суммируются в parent; SUPPORT помечаются DONE.
- Конвертация ресурсов экшена в очки атаки/обороны по JSON-курсу (см. config/combat_rates.json).
- Бонус "on point": +20 очков. Если в районе одновременно есть on_point атака и on_point оборона — район становится «спорным» и в этом цикле не обрабатывается и не выдаёт ресурсы.
- Динамический пересчёт resource_multiplier для каждого района перед выдачей ресурсов на основе близости идеологий владельца района и «прикреплённого» к району политика:
    diff = |owner.ideology - politician.ideology| в диапазоне [0..10],
    multiplier = 1.20 - 0.08 * diff  ∈ [0.40 .. 1.20] (линейная шкала).
- ОСТАТОК ОБОРОНЫ → В ОЧКИ КОНТРОЛЯ: после расчёта атак вся оставшаяся оборона района добавляется к District.control_points.
"""

import asyncio
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from db.models import (
    Base,
    User,
    District,
    Action,
    News,
    Politician,
    ActionStatus,
    ActionType,
)

from openpyxl import Workbook, load_workbook   # NEW

CYCLE_TS: Optional[str] = None                  # NEW
CYCLE_XLSX_PATH: Optional[Path] = None          # NEW
NEWS_HEADERS = ["created_at_utc", "tag", "title", "body", "action_id", "district_id"]  # NEW

# -------- Настройки --------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./game.db")
COMBAT_RATES_PATH = os.getenv("COMBAT_RATES_PATH", "./config/combat_rates.json")

ATTACK_KIND = "attack"
DEFENSE_KIND = "defense"
SCOUT_KINDS = {"scout_dist", "scout_info"}

ORDER_ATTACKS_ASC = True  # порядок атак по created_at


# -------- Логгер --------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("game_cycle")

def _ensure_sheet(wb: Workbook, name: str, headers: List[str]) -> None:
    if name not in wb.sheetnames:
        ws = wb.create_sheet(title=name)
        ws.append(headers)

def _ensure_cycle_workbook() -> Path:
    """Создаёт (при необходимости) XLSX для текущего цикла и возвращает путь к нему."""
    global CYCLE_XLSX_PATH
    if not CYCLE_TS:
        raise RuntimeError("CYCLE_TS не задан. Устанавливается в начале run_game_cycle().")
    path = Path(f"./exports/{CYCLE_TS}.xlsx")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "news"
        ws.append(NEWS_HEADERS)
        wb.save(path)
    CYCLE_XLSX_PATH = path
    return path

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CombatRates:
    attack: Dict[str, float]
    defense: Dict[str, float]
    on_point_bonus: int = 20

    @staticmethod
    def load(path: str) -> "CombatRates":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Combat rates file not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        return CombatRates(
            attack=data.get("attack", {}),
            defense=data.get("defense", {}),
            on_point_bonus=int(data.get("on_point_bonus", 20)),
        )


# ====== NEWS HELPERS ======
async def add_news(
    session: AsyncSession,
    title: str,
    body: str,
    action_id: Optional[int] = None,
    *,
    district_id: Optional[int] = None,
    tag: str = "auto generated",
):
    """Пишет строку новости в общий лист 'news' и (если district_id задан) в лист района."""
    path = _ensure_cycle_workbook()
    wb = load_workbook(path)

    # общий лист
    _ensure_sheet(wb, "news", NEWS_HEADERS)
    wb["news"].append([now_utc().isoformat(), tag, title, body, action_id, district_id])

    # лист конкретного района
    if district_id is not None:
        sheet_name = f"district_{district_id}"
        _ensure_sheet(wb, sheet_name, NEWS_HEADERS)
        wb[sheet_name].append([now_utc().isoformat(), tag, title, body, action_id, district_id])

    wb.save(path)

# ====== SUPPORT AGGREGATION ======
async def aggregate_supports(session: AsyncSession) -> Tuple[List[int], List[int]]:
    """
    Суммирует все SUPPORT-действия (status=PENDING) в их parent_action.
    Возвращает:
        (список id обработанных SUPPORT, список id parent, в которые агрегировали)
    """
    stmt = select(Action).where(
        Action.status == ActionStatus.PENDING,
        Action.parent_action_id.is_not(None),
        Action.type == ActionType.SUPPORT,
    )
    res = await session.execute(stmt)
    supports: List[Action] = list(res.scalars().all())
    if not supports:
        return [], []

    # Группируем по parent_action_id
    by_parent: Dict[int, List[Action]] = defaultdict(list)
    for s in supports:
        if s.parent_action_id:
            by_parent[s.parent_action_id].append(s)

    parent_ids: List[int] = list(by_parent.keys())

    # Загрузим родителей
    q = await session.execute(select(Action).where(Action.id.in_(parent_ids)))
    parents: Dict[int, Action] = {a.id: a for a in q.scalars().all()}

    processed_support_ids: List[int] = []
    touched_parents: List[int] = []

    for pid, group in by_parent.items():
        parent = parents.get(pid)
        if not parent or parent.status != ActionStatus.PENDING:
            # Если родитель уже неактивен — просто пометим supports как DONE (или FAILED по вашей бизнес-логике)
            for s in group:
                processed_support_ids.append(s.id)
            continue

        total_force = sum(max(0, int(s.force)) for s in group)
        total_money = sum(max(0, int(s.money)) for s in group)
        total_infl  = sum(max(0, int(s.influence)) for s in group)
        total_info  = sum(max(0, int(s.information)) for s in group)

        parent.force       += total_force
        parent.money       += total_money
        parent.influence   += total_infl
        parent.information += total_info

        touched_parents.append(parent.id)
        processed_support_ids.extend([s.id for s in group])

    await session.commit()

    if processed_support_ids:
        await session.execute(
            update(Action)
            .where(Action.id.in_(processed_support_ids))
            .values(status=ActionStatus.DONE, updated_at=now_utc())
        )
        await session.commit()


    return processed_support_ids, touched_parents


# ====== RESOURCE->POINTS ======
def resources_to_points(kind: str, action: Action, rates: CombatRates) -> int:
    """
    Конвертирует ресурсы экшена в очки по курсу.
    kind ∈ {'attack','defense'}
    + on_point бонус.
    """
    table = rates.attack if kind == ATTACK_KIND else rates.defense
    # несуществующие ключи считаем с весом 0
    force_w = float(table.get("force", 0))
    money_w = float(table.get("money", 0))
    infl_w  = float(table.get("influence", 0))
    info_w  = float(table.get("information", 0))

    pts = (
        max(0, int(action.force))       * force_w +
        max(0, int(action.money))       * money_w +
        max(0, int(action.influence))   * infl_w +
        max(0, int(action.information)) * info_w
    )
    pts = int(round(pts))
    if action.on_point:
        pts += rates.on_point_bonus
    return max(0, pts)


# ====== CONTESTED DETECTION ======
async def detect_contested_districts(session: AsyncSession) -> List[int]:
    """
    Если в районе есть и on_point-атака, и on_point-оборона (в статусе PENDING),
    район считается «спорным». Такие районы в этом цикле:
      - не резолвим,
      - не начисляем ресурсы.
    """
    # on_point атаки
    stmt_att = select(Action.district_id).where(
        Action.status == ActionStatus.PENDING,
        Action.kind == ATTACK_KIND,
        Action.on_point.is_(True),
        Action.district_id.is_not(None),
    )
    # on_point защиты
    stmt_def = select(Action.district_id).where(
        Action.status == ActionStatus.PENDING,
        Action.kind == DEFENSE_KIND,
        Action.on_point.is_(True),
        Action.district_id.is_not(None),
    )
    att = await session.execute(stmt_att)
    defs = await session.execute(stmt_def)
    att_set = set(x for x in att.scalars().all() if x is not None)
    def_set = set(x for x in defs.scalars().all() if x is not None)
    contested = sorted(att_set & def_set)
    return contested


# ====== DEFENSE POOLS ======
# ЗАМЕНА функции resolve_defense_pools в game_cycle.py

async def resolve_defense_pools(session: AsyncSession, rates: CombatRates, contested: List[int]) -> Dict[int, int]:
    """
    Формирует стартовый пул обороны ИЗ ТЕКУЩИХ control_points районов (кроме спорных),
    затем добавляет к нему очки из pending-действий kind='defense' (с конверсией ресурсов и on_point бонусом).

    Возвращает словарь district_id -> defense_points.
    Использованные defense-экшены помечаются DONE.
    Спорные районы пропускаются полностью (их control_points не трогаем).
    """
    contested_set = set(contested)

    # 0) Стартовая оборона из control_points
    q = await session.execute(select(District))
    districts: List[District] = list(q.scalars().all())

    defense_pool: Dict[int, int] = defaultdict(int)
    seeded_from_cp: Dict[int, int] = {}

    for d in districts:
        if d.id in contested_set:
            continue
        if d.control_points > 0:
            defense_pool[d.id] += int(d.control_points)
            seeded_from_cp[d.id] = int(d.control_points)
            # контрольные очки "уходят" в оборону на этот цикл
            d.control_points = 0

    if seeded_from_cp:
        await session.commit()

    # 1) Прибавляем оборону из pending defense-экшенов (учёт курсов и on_point)
    stmt = (
        select(Action)
        .where(
            Action.status == ActionStatus.PENDING,
            Action.kind == DEFENSE_KIND,
            Action.district_id.is_not(None),
        )
        .order_by(Action.id.asc())
    )
    res = await session.execute(stmt)
    actions: List[Action] = list(res.scalars().all())

    used_ids: List[int] = []
    for a in actions:
        did = a.district_id
        if did is None or did in contested_set:
            continue
        pts = resources_to_points(DEFENSE_KIND, a, rates)
        defense_pool[did] += pts
        used_ids.append(a.id)

    if used_ids:
        await session.execute(
            update(Action)
            .where(Action.id.in_(used_ids))
            .values(status=ActionStatus.DONE, updated_at=now_utc())
        )
        await session.commit()

    if defense_pool:
        log.info("Итоги обороны по районам (очки): %s", dict(defense_pool))

    return dict(defense_pool)



# ====== ATTACK RESOLUTION ======
async def resolve_attacks(session: AsyncSession, rates: CombatRates, defense_pool: Dict[int, int], contested: List[int]):
    """
    Пошагово резолвит атаки (kind='attack', status=PENDING) с учётом defense_pool.
    Пропускает «спорные» районы.
    """
    base_stmt = (
        select(Action)
        .where(Action.status == ActionStatus.PENDING, Action.kind == ATTACK_KIND, Action.district_id.is_not(None))
    )
    base_stmt = base_stmt.order_by(Action.created_at.asc() if ORDER_ATTACKS_ASC else Action.created_at.desc())
    res = await session.execute(base_stmt)
    attacks: List[Action] = list(res.scalars().all())

    if not attacks:
        log.info("Атак для резолва нет.")
        return

    by_district: Dict[int, List[Action]] = defaultdict(list)
    for a in attacks:
        if a.district_id:
            by_district[a.district_id].append(a)

    district_cache: Dict[int, District] = {}
    user_cache: Dict[int, User] = {}

    async def get_district(did: int) -> Optional[District]:
        if did not in district_cache:
            d = await District.get_by_id(session, did)
            if d:
                district_cache[did] = d
            else:
                return None
        return district_cache[did]

    async def get_user(uid: int) -> Optional[User]:
        if uid not in user_cache:
            q = await session.execute(select(User).where(User.id == uid))
            user = q.scalars().first()
            if user:
                user_cache[uid] = user
            else:
                return None
        return user_cache[uid]

    processed_ids: List[int] = []
    ownership_changes = 0

    for district_id, attack_list in by_district.items():
        if district_id in contested:
            # район пропускаем полностью
            continue

        d = await get_district(district_id)
        if not d:
            for a in attack_list:
                processed_ids.append(a.id)
            continue

        current_def = int(defense_pool.get(district_id, 0))

        for a in attack_list:
            power_pts = resources_to_points(ATTACK_KIND, a, rates)
            attacker = await get_user(a.owner_id)
            attacker_name = (
                        attacker.in_game_name or attacker.username or f"User#{attacker.id}") if attacker else "Неизвестный"
            attacker_faction = (attacker.faction or "без фракции") if attacker else "неизвестно"

            if power_pts <= current_def:
                current_def -= power_pts
                await add_news(
                    session,
                    title=f"Отражена атака на район '{d.name}'",
                    body=(
                        f"Атака игрока {attacker_name} ({power_pts} очков) была отражена. "
                        f"Фракция атакующего: {attacker_faction}. "
                        f"Текущая оборона района: {current_def}."
                    ),
                    action_id=a.id,
                    district_id=d.id,
                )
            else:
                overflow = power_pts - current_def
                d = await District.reassign_owner(session, district_id=district_id, new_owner_id=a.owner_id)
                district_cache[district_id] = d
                current_def = overflow  # остаток становится новой «обороной»
                ownership_changes += 1

                await add_news(
                    session,
                    title=f"Район '{d.name}' захвачен!",
                    body=(
                        f"Атака игрока {attacker_name} ({power_pts} очков) прорвала оборону района. "
                        f"Фракция захватившего: {attacker_faction}. "
                        f"Новый владелец — {attacker_name}. Остаток {overflow} очков укрепил оборону района."
                    ),
                    action_id=a.id,
                    district_id=d.id,
                )
            processed_ids.append(a.id)

        defense_pool[district_id] = current_def

    if processed_ids:
        await session.execute(
            update(Action).where(Action.id.in_(processed_ids)).values(status=ActionStatus.DONE, updated_at=now_utc())
        )
        await session.commit()


# ====== LEFTOVER DEFENSE -> CONTROL POINTS ======
async def convert_leftover_defense_to_control_points(
    session: AsyncSession,
    defense_pool: Dict[int, int],
    contested: List[int],
) -> None:
    """
    Вся оставшаяся после расчёта атак оборона района добавляется к District.control_points.
    Спорные районы пропускаются.
    """
    if not defense_pool:
        return

    contested_set = set(contested)
    updated: Dict[int, int] = {}

    for district_id, remaining_def in defense_pool.items():
        if remaining_def <= 0 or district_id in contested_set:
            continue
        d = await District.get_by_id(session, district_id)
        if not d:
            continue
        d.control_points += int(remaining_def)
        updated[district_id] = int(remaining_def)

    if updated:
        await session.commit()

# ====== SCOUT CLOSE ======
async def close_all_scouting(session: AsyncSession):
    stmt = select(Action.id).where(Action.status == ActionStatus.PENDING, Action.kind.in_(SCOUT_KINDS))
    res = await session.execute(stmt)
    ids = [row for row in res.scalars().all()]
    if not ids:
        return
    await session.execute(
        update(Action).where(Action.id.in_(ids)).values(status=ActionStatus.DONE, updated_at=now_utc())
    )
    await session.commit()

# ====== RESOURCE MULTIPLIER BY IDEOLOGY ======
def ideology_multiplier(owner_ideol: int, pol_ideol: Optional[int]) -> float:
    """
    Линейная шкала по модулю разницы (0..10):
      diff=0  -> 1.20
      diff=10 -> 0.40
      шаг 0.08 за единицу diff.
    Если политика нет — возвращаем 1.0 (и multiplier не меняем).
    """
    if pol_ideol is None:
        return 1.0
    diff = abs(int(owner_ideol) - int(pol_ideol))  # 0..10
    diff = max(0, min(10, diff))
    return 1.20 - 0.08 * diff


async def recalc_resource_multipliers(session: AsyncSession):
    """
    Перед начислением ресурсов обновляет district.resource_multiplier согласно близости
    owner.ideology и politician.ideology. Если политика нет — multiplier не меняем.
    """
    q = await session.execute(select(District))
    districts: List[District] = list(q.scalars().all())
    if not districts:
        return

    owner_cache: Dict[int, User] = {}
    pol_by_district: Dict[int, Optional[Politician]] = {}

    for d in districts:
        if d.owner_id not in owner_cache:
            uq = await session.execute(select(User).where(User.id == d.owner_id))
            owner_cache[d.owner_id] = uq.scalars().first()

        pq = await session.execute(select(Politician).where(Politician.district_id == d.id))
        pol = pq.scalars().first()
        pol_by_district[d.id] = pol

    updated = 0
    for d in districts:
        owner = owner_cache.get(d.owner_id)
        pol = pol_by_district.get(d.id)
        if owner and pol:
            mul = ideology_multiplier(owner.ideology, pol.ideology)
            mul = max(0.40, min(1.20, mul))
            if abs(d.resource_multiplier - mul) > 1e-6:
                d.resource_multiplier = mul
                updated += 1

    if updated:
        await session.commit()


# ====== GRANT RESOURCES ======
async def grant_district_resources(session: AsyncSession, contested: List[int]):
    """
    Начисляет владельцам ресурсы с районов, исключая «спорные» районы.
    Предварительно должен быть вызван recalc_resource_multipliers().
    """
    res = await session.execute(select(District))
    districts: List[District] = list(res.scalars().all())
    if not districts:
        return

    contested_set = set(contested)
    changes: Dict[int, dict] = defaultdict(lambda: {"money": 0, "influence": 0, "information": 0, "force": 0})
    for d in districts:
        if d.id in contested_set:
            continue
        eff = d.effective_resources()
        changes[d.owner_id]["money"] += eff["money"]
        changes[d.owner_id]["influence"] += eff["influence"]
        changes[d.owner_id]["information"] += eff["information"]
        changes[d.owner_id]["force"] += eff["force"]

    total_money = total_infl = total_info = total_force = 0
    for uid, delta in changes.items():
        uq = await session.execute(select(User).where(User.id == uid))
        user = uq.scalars().first()
        if not user:
            continue
        user.money       += delta["money"]
        user.influence   += delta["influence"]
        user.information += delta["information"]
        user.force       += delta["force"]

        total_money += delta["money"]
        total_infl  += delta["influence"]
        total_info  += delta["information"]
        total_force += delta["force"]

    await session.commit()


# ====== REFRESH PLAYER ACTION SLOTS ======
async def refresh_player_actions(session: AsyncSession):
    res = await session.execute(select(User))
    users: List[User] = list(res.scalars().all())
    if not users:
        return

    refreshed = 0
    for u in users:
        max_actions = u.max_available_actions or 0
        if u.available_actions < max_actions:
            u.available_actions = max_actions
            u.actions_refresh_at = now_utc()
            refreshed += 1

    await session.commit()


# ====== MAIN ======
async def run_game_cycle():
    global CYCLE_TS
    rates = CombatRates.load(COMBAT_RATES_PATH)

    # фиксируем timestamp цикла и создаём файл
    CYCLE_TS = now_utc().strftime("%Y%m%dT%H%M%SZ")
    _ensure_cycle_workbook()
    log.info(f"Файл отчёта цикла: {CYCLE_TS}.xlsx")

    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async_session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session_factory() as session:
        log.info("=== Старт игрового цикла ===")

        # A) Сначала агрегируем SUPPORT → parent
        await aggregate_supports(session)

        # B) Определяем «спорные» районы
        contested = await detect_contested_districts(session)

        # 1) Резолв обороны (в очках, конверсия по rates)
        defense_pool = await resolve_defense_pools(session, rates, contested)

        # 2) Резолв атак (one-by-one per district, в очках)
        await resolve_attacks(session, rates, defense_pool, contested)

        # 2.5) Остаток обороны → очки контроля
        await convert_leftover_defense_to_control_points(session, defense_pool, contested)

        # 3) Закрыть все разведки
        await close_all_scouting(session)

        # 4) Пересчитать resource_multiplier на основе идеологий (владелец ↔ политик)
        await recalc_resource_multipliers(session)

        # 5) Выдать владельцам ресурсы районов (исключая спорные районы)
        await grant_district_resources(session, contested)

        # 6) Обновить доступные действия игрокам
        await refresh_player_actions(session)

        # 7) Финальная новость
        log.info("=== Игровой цикл завершён ===")


if __name__ == "__main__":
    asyncio.run(run_game_cycle())
