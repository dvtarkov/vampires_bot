import logging
from aiogram import Router, types, F
from options.registry import get_option

router = Router()

@router.callback_query(F.data)
async def handle_any_option(cb: types.CallbackQuery):
    key = cb.data or ""
    func = get_option(key)
    if not func:
        logging.warning("Unknown option callback: %s", key)
        await cb.answer("Неизвестная команда.", show_alert=False)
        return

    try:
        await func(cb)  # по соглашению, в обработчик передаём сам CallbackQuery
    except Exception as e:
        logging.exception("Option handler failed: %s", key)
        await cb.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
