import logging
from time import monotonic
from aiogram import BaseMiddleware


class TimingMW(BaseMiddleware):
    async def __call__(self, handler, event, data):
        t0 = monotonic()
        try:
            return await handler(event, data)
        finally:
            dt = (monotonic() - t0) * 1000
            logging.info("Handled %s in %.1f ms", type(event).__name__, dt)

