import os
from dataclasses import dataclass
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()


@dataclass
class DBConfig:
    url: str


def load_db_config() -> DBConfig:
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    return DBConfig(url=url)
