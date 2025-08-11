import os
import logging
from logging.handlers import TimedRotatingFileHandler


class LevelFilter(logging.Filter):
    def __init__(self, low: int, high: int):
        super().__init__()
        self.low = low
        self.high = high

    def filter(self, record: logging.LogRecord) -> bool:
        return self.low <= record.levelno <= self.high


def setup_logging(level: str = "INFO"):
    os.makedirs("logs", exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root = logging.getLogger()
    root.setLevel(level)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    ih = TimedRotatingFileHandler("logs/bot.info.log", when="midnight", backupCount=3, encoding="utf-8")
    ih.setLevel(logging.INFO)
    ih.setFormatter(fmt)
    ih.addFilter(LevelFilter(logging.INFO, logging.INFO))
    root.addHandler(ih)

    wh = TimedRotatingFileHandler("logs/bot.warning.log", when="midnight", backupCount=3, encoding="utf-8")
    wh.setLevel(logging.WARNING)
    wh.setFormatter(fmt)
    wh.addFilter(LevelFilter(logging.WARNING, logging.WARNING))
    root.addHandler(wh)

    eh = TimedRotatingFileHandler("logs/bot.error.log", when="midnight", backupCount=3, encoding="utf-8")
