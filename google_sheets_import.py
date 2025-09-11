# import_all_from_sheets.py
import importlib
import os, json, asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Type, Optional
from sqlalchemy import Integer, BigInteger, Float, Boolean, DateTime, String, Text, JSON as SAJSON, Enum as SAEnum
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from dateutil.parser import isoparse

from sqlalchemy import select, update, insert, ColumnDefault
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# === ваш Base ===
from db.session import Base

# ВАЖНО: загрузить модели, чтобы мапперы зарегистрировались
importlib.import_module("db.models")

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
DB_URL = os.environ["DATABASE_URL"]
SA_PATH = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
def is_empty_cell(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        s = val.strip()
        if s == "": return True
        if s.lower() in {"none", "null", "nan", "n/a"}: return True
        if s in {"-", "—"}: return True
    return False

def is_non_nullable(col) -> bool:
    # nullable=False и нет server_default ⇒ нельзя писать None
    return not getattr(col, "nullable", True) and getattr(col, "server_default", None) is None

def get_python_default(sa_col):
    """
    Возвращает python default, заданный в модели (Column(default=...)),
    если он есть. Работает для литерала и callables.
    """
    d = sa_col.default
    if not isinstance(d, ColumnDefault):
        return None
    arg = d.arg
    try:
        return arg() if callable(arg) else arg
    except Exception:
        return None



def now_utc() -> datetime:
    return datetime.now(timezone.utc)

# -------------------- Вспомогалки --------------------
def get_models(base: Type[DeclarativeBase]) -> List[Type]:
    models = []
    for m in base.registry.mappers:
        cls = m.class_
        if hasattr(cls, "__table__"):
            models.append(cls)
    models.sort(key=lambda c: getattr(c, "__tablename__", c.__name__))
    return models

def is_rel_name_col(col: str) -> bool:
    # игнорим relationship-колонки вида owner__name, scouting_by__names и т.п.
    return "__name" in col

def sheet_to_dataframe(gc: gspread.Client, title: str) -> Optional[pd.DataFrame]:
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return None
    values = ws.get_all_values()  # [[col1, col2, ...], [...], ...]
    if not values:
        return pd.DataFrame()
    header = values[0]
    rows = values[1:] if len(values) > 1 else []
    return pd.DataFrame(rows, columns=header)

# Приведение типов по колонке SQLAlchemy
def convert_value(sa_col, val: Any):
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None

    coltype = sa_col.type

    if isinstance(coltype, SAEnum):
        return val  # оставляем строку как есть (как экспортировали)

    if isinstance(coltype, (Integer, BigInteger)):
        try:
            return int(str(val).strip())
        except Exception:
            return None

    if isinstance(coltype, Float):
        s = str(val).strip().replace(",", ".")
        try:
            if s.endswith("%"):
                s = s[:-1].strip()
                return float(s) / 100.0
            return float(s)
        except Exception:
            return None

    if isinstance(coltype, Boolean):
        s = str(val).strip().lower()
        if s in ("1", "true", "t", "yes", "y", "да"): return True
        if s in ("0", "false", "f", "no", "n", "нет"): return False
        return None

    if isinstance(coltype, DateTime):
        from dateutil.parser import isoparse
        try:
            return isoparse(val) if isinstance(val, str) else val
        except Exception:
            return None

    if isinstance(coltype, SAJSON):
        if isinstance(val, (dict, list)): return val
        try:
            return json.loads(val)
        except Exception:
            return None

    if isinstance(coltype, (String, Text)):
        return str(val)

    return val

def model_columns_dict(model: Type):
    # name -> Column
    return {c.name: c for c in model.__table__.columns}

async def upsert_rows(session: AsyncSession, model: Type, df: pd.DataFrame):
    cols = model_columns_dict(model)

    has_created = "created_at" in cols
    has_updated = "updated_at" in cols
    id_col_present = "id" in cols

    # берём только реальные колонки модели и игнорим __name/__names
    valid_cols = [c for c in df.columns if c in cols and not is_rel_name_col(c)]

    def build_update_payload(row: pd.Series) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for c in valid_cols:
            raw = row[c]
            if is_empty_cell(raw):
                continue  # пусто -> не трогаем колонку
            val = convert_value(cols[c], raw)

            # если конвертация дала None и колонка NOT NULL — не трогаем её
            if val is None and is_non_nullable(cols[c]):
                continue

            payload[c] = val
        if has_updated:
            payload["updated_at"] = now_utc()
        if has_created:
            payload["created_at"] = now_utc()
        return payload

    def build_insert_payload(row: pd.Series) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for c in valid_cols:
            raw = row[c]
            if is_empty_cell(raw):
                # попробуем подставить python-default из модели
                pdflt = get_python_default(cols[c])
                if pdflt is not None:
                    payload[c] = pdflt
                # иначе не кладём ключ — пусть БД/серверный default сработает,
                # либо проверим позже обязательность
                continue
            payload[c] = convert_value(cols[c], raw)

        # server time
        if has_updated:
            payload["updated_at"] = now_utc()
        if has_created:
            payload["created_at"] = now_utc()

        # Для non-nullable колонок без значения и без server_default —
        # подставим python-default, если есть. Если нет — оставим как есть:
        # SQLite/PG упадут понятной ошибкой, что поможет увидеть,
        # какой столбец обязателен.
        for name, c in cols.items():
            if name in payload or is_rel_name_col(name):
                continue
            if not getattr(c, "nullable", True) and c.server_default is None:
                pdflt = get_python_default(c)
                if pdflt is not None:
                    payload[name] = pdflt
        return payload

    to_update, to_insert = [], []
    for _, row in df.iterrows():
        rid = None
        if id_col_present:
            raw_id = row.get("id", None)
            try:
                rid = int(raw_id) if not is_empty_cell(raw_id) else None
            except Exception:
                rid = None

        if rid:
            p = build_update_payload(row)
            p["id"] = rid
            to_update.append(p)
        else:
            p = build_insert_payload(row)
            # не тянем id=None в вставку
            p.pop("id", None)
            to_insert.append(p)

    # UPDATE существующих
    if to_update:
        ids = [p["id"] for p in to_update]
        res = await session.execute(select(model.id).where(model.id.in_(ids)))
        present_ids = set(int(x) for x in res.scalars().all())

        for p in to_update:
            rid = p.pop("id")
            if not p:
                # нечего обновлять (все клетки пустые) — пропускаем
                continue
            if rid in present_ids:
                await session.execute(
                    update(model)
                    .where(model.id == rid)
                    .values(**p)
                    .execution_options(synchronize_session="fetch")
                )
            else:
                # нет записи — вставим c явным id
                await session.execute(insert(model).values(id=rid, **p))

    # INSERT новых
    for p in to_insert:
        await session.execute(insert(model).values(**p))

    await session.commit()


# -------------------- Основная точка входа --------------------
async def import_model(session: AsyncSession, gc: gspread.Client, model: Type):
    tablename = getattr(model, "__tablename__", model.__name__)
    df = sheet_to_dataframe(gc, tablename)
    if df is None:
        print(f"[SKIP] Нет листа '{tablename}', пропускаю")
        return
    if df.empty:
        print(f"[OK] {tablename}: лист пуст — ничего импортировать")
        return

    # Убедимся, что все названия колонок уникальны
    if len(set(df.columns)) != len(df.columns):
        raise RuntimeError(f"{tablename}: в шапке листа есть дубликаты колонок")

    await upsert_rows(session, model, df)
    print(f"[OK] {tablename}: импорт завершён (rows={len(df)})")

async def main():
    # DB
    engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Google
    creds = Credentials.from_service_account_file(SA_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)

    models = get_models(Base)
    if not models:
        raise RuntimeError("Не найдено ORM-моделей на Base")

    async with async_session() as session:
        for model in models:
            await import_model(session, gc, model)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
