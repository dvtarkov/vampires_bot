# routes/options.py
import logging, inspect
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from options.registry import get_option
from utils.callback import parse_callback_data  # если используешь разбор ?k=v

router = Router()


@router.callback_query(F.data)
async def handle_any_option(cb: types.CallbackQuery, state: FSMContext):
    key, cb_kwargs = parse_callback_data(cb.data or "")
    func = get_option(key)
    if not func:
        logging.warning("Unknown option callback: %s", key)
        await cb.answer("Неизвестная команда.", show_alert=False)
        return

    try:
        sig = inspect.signature(func)
        params = sig.parameters
        accepts_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())

        call_kwargs = {}
        if "cb" in params:
            call_kwargs["cb"] = cb
        if "state" in params:
            call_kwargs["state"] = state

        if accepts_kwargs:
            call_kwargs.update(cb_kwargs)
        else:
            for name, val in cb_kwargs.items():
                if name in params:
                    call_kwargs[name] = val

        result = await func(**call_kwargs)
        return result
    except Exception:
        logging.exception("Option handler failed: %s (%s)", key, cb_kwargs)
        await cb.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
