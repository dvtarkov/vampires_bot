# export_all_to_sheets_rel.py
import importlib
import os, json, asyncio
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Type

import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials

from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import selectinload  # ВАЖНО для подгрузки связей одним махом

# ==== ваш Base ====
from db.session import Base

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
DB_URL = os.environ["DATABASE_URL"]
SA_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
importlib.import_module("db.models")
# ---------- утилиты ----------
def to_jsonable(v: Any) -> Any:
    if v is None: return None
    if isinstance(v, (int, float, str, bool)): return v
    if isinstance(v, (datetime, date)): return v.isoformat()
    if isinstance(v, Decimal): return str(v)
    if hasattr(v, "value"):  # Enum
        try: return v.value
        except Exception: pass
    try:
        return json.dumps(v, ensure_ascii=False)
    except Exception:
        return str(v)

def humanize(obj: Any) -> str:
    """Как показывать 'имя' связанного объекта."""
    if obj is None:
        return ""
    cls = obj.__class__.__name__.lower()

    # User
    if hasattr(obj, "tg_id") and hasattr(obj, "username"):
        if getattr(obj, "in_game_name", None):
            return str(obj.in_game_name)
        if getattr(obj, "username", None):
            return f"@{obj.username}"
        fn = getattr(obj, "first_name", "") or ""
        ln = getattr(obj, "last_name", "") or ""
        full = (fn + " " + ln).strip()
        return full or f"tg:{getattr(obj, 'tg_id', '')}"

    # District
    if hasattr(obj, "name") and hasattr(obj, "owner_id"):
        return str(getattr(obj, "name", ""))

    # Action
    if hasattr(obj, "title") and hasattr(obj, "status"):
        return str(getattr(obj, "title", "") or f"Action#{getattr(obj, 'id', '')}")

    # News
    if hasattr(obj, "body") and hasattr(obj, "title"):
        return str(getattr(obj, "title", ""))

    # Politician
    if hasattr(obj, "role_and_influence") and hasattr(obj, "name"):
        return str(getattr(obj, "name", ""))

    # Fallbacks
    if hasattr(obj, "name"): return str(getattr(obj, "name"))
    if hasattr(obj, "title"): return str(getattr(obj, "title"))
    if hasattr(obj, "id"): return f"#{getattr(obj, 'id')}"
    return str(obj)

def get_models(base: Type[DeclarativeBase]) -> List[Type]:
    models = []
    for m in base.registry.mappers:
        cls = m.class_
        if hasattr(cls, "__table__"):
            models.append(cls)
    models.sort(key=lambda c: getattr(c, "__tablename__", c.__name__))
    return models

def column_names(model: Type) -> List[str]:
    return [c.name for c in model.__table__.columns]

def relationship_specs(model: Type):
    """
    Возвращает список (rel_key, uselist) для всех relationship у модели.
    Пропускаем backref-only/динамические, но обычные selectin/joined — берём.
    """
    rels = []
    for rel in model.__mapper__.relationships:
        # можно отфильтровать служебные при желании
        rels.append((rel.key, rel.uselist))
    return rels

def build_query_with_rels(model: Type):
    """SELECT модели + selectinload всех её связей, чтобы не ловить N+1."""
    from sqlalchemy import select as sa_select
    stmt = sa_select(model)
    for rel in model.__mapper__.relationships:
        stmt = stmt.options(selectinload(getattr(model, rel.key)))
    return stmt

def get_ws(gc: gspread.Client, spreadsheet_id: str, title: str, ncols: int) -> gspread.Worksheet:
    sh = gc.open_by_key(spreadsheet_id)
    from gspread.exceptions import WorksheetNotFound
    try:
        ws = sh.worksheet(title)
        ws.clear()
        ws.resize(rows=1, cols=max(ncols, 1))
        return ws
    except WorksheetNotFound:
        return sh.add_worksheet(title=title[:100], rows=1, cols=max(ncols, 1))

# ---------- сборка строк ----------
def objects_to_dataframe(objs: List[Any], cols: List[str], rels: List[tuple]) -> pd.DataFrame:
    extended_cols = cols.copy()
    # добавляем колонки для связей
    for key, uselist in rels:
        extended_cols.append(f"{key}__names" if uselist else f"{key}__name")

    rows = []
    for obj in objs:
        row: Dict[str, Any] = {}
        # БД-колонки 1:1
        for c in cols:
            row[c] = to_jsonable(getattr(obj, c))

        # Связи → имена
        for key, uselist in rels:
            rel_val = getattr(obj, key)
            if uselist:
                names = [humanize(x) for x in (rel_val or [])]
                row[f"{key}__names"] = "; ".join([n for n in names if n])
            else:
                row[f"{key}__name"] = humanize(rel_val)

        rows.append(row)

    return pd.DataFrame(rows, columns=extended_cols)

# ---------- основной экспорт ----------
async def export_model(session: AsyncSession, gc: gspread.Client, model: Type):
    tablename = getattr(model, "__tablename__", model.__name__)
    cols = column_names(model)
    rels = relationship_specs(model)

    stmt = build_query_with_rels(model)
    res = await session.execute(stmt)
    objs = list(res.scalars().all())

    df = objects_to_dataframe(objs, cols, rels)
    ws = get_ws(gc, SPREADSHEET_ID, tablename, ncols=len(df.columns))
    set_with_dataframe(ws, df, include_index=False, include_column_header=True, resize=True)
    print(f"[OK] {tablename}: {len(df)} rows, {len(df.columns)} columns (with relationships)")

async def main():
    engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    creds = Credentials.from_service_account_file(SA_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)

    models = get_models(Base)
    if not models:
        raise RuntimeError("Нет ORM-моделей на Base")

    async with async_session() as session:
        for model in models:
            await export_model(session, gc, model)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
