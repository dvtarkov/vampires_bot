import asyncio
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine
from alembic import context

from db.session import Base
from db.config import load_db_config
import db.models  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", load_db_config().url)
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,  # оставь True для SQLite
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = AsyncEngine(
        engine_from_config(
            config.get_section(config.config_ini_section) or {},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
        )
    )

    def do_configure(connection):
        """Эта функция получает sync-connection от run_sync."""
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,  # для SQLite можно оставить
        )

    def do_run_migrations(connection):
        """Выполняем миграции уже в синхронном контексте Alembic."""
        do_configure(connection)
        with context.begin_transaction():
            context.run_migrations()

    async def async_main():
        async with connectable.connect() as async_conn:
            await async_conn.run_sync(do_run_migrations)

    asyncio.run(async_main())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
