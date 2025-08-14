from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from db.config import load_db_config


class Base(DeclarativeBase):
    pass


_db_cfg = load_db_config()
engine = create_async_engine(_db_cfg.url, echo=False, future=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

# Утилита для контекстного использования
from contextlib import asynccontextmanager


@asynccontextmanager
async def get_session():
    async with SessionLocal() as session:
        yield session
