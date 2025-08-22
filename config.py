import os
from dataclasses import dataclass
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()


@dataclass
class Config:
    bot_token: str
    log_level: str = "INFO"
    default_localization: str = "en"
    template_root: str = "templates"
    bot_name: str = ""


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set in environment or .env")

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    default_localization = os.getenv("DEFAULT_LOCALIZATION", "en").lower()
    template_root = os.getenv("TEMPLATE_ROOT", "templates")
    bot_name = os.getenv("BOT_NAME", "")
    return Config(
        bot_token=bot_token,
        log_level=log_level,
        default_localization=default_localization,
        template_root=template_root,
        bot_name=bot_name,
    )
