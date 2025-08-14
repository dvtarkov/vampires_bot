import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from text_handlers import get_text_handler, _REGISTRY
from aiogram.filters import StateFilter
router = Router()


@router.message(StateFilter("*"), F.text)
async def any_text_with_state(message: types.Message, state: FSMContext):
    state_key = await state.get_state()  # строка "Package:state_name" или None
    logging.info(f"Handling some state with state_key: {state_key}, in state {state.set_state()}")
    if not state_key:
        # у пользователя нет стейта — пропускаем, пусть другие хэндлеры обрабатывают
        return
    logging.info("FSM state: %s; registry: %s", state_key, list(_REGISTRY.keys()))

    handler = get_text_handler(state_key)

    await state.clear()

    try:
        if not handler:
            logging.warning("No text_handler for state=%s", state_key)
            # тут можно показать ваш универсальный экран ошибки, если нужно
            await message.answer("Неизвестный ввод для текущего шага. Попробуйте ещё раз.")
            return

        # вызываем зарегистрированный хэндлер
        await handler(message=message, state=state)

    except Exception as e:
        logging.exception("Text handler failed for state=%s", state_key)
        # тут тоже можно вызвать ваш ErrorScreen
        await message.answer(f"Ошибка: {e}")


# --- 1) Любые КОМАНДЫ (если не перехвачены раньше) ---
@router.message(F.text.regexp(r"^/\w+"))
async def any_command(message: types.Message):
    cmd = (message.text or "").split()[0]
    logging.info("Fallback command handler: %s from user_id=%s", cmd, message.from_user.id)
    await message.answer(f"Команда `{cmd}` не поддерживается.")


# --- 3) Любые СООБЩЕНИЯ ---
@router.message()
async def any_message(message: types.Message):
    text = message.text or message.caption or "<non-text>"
    logging.info("Fallback message handler: text=%s from user_id=%s", text, message.from_user.id)
    await message.answer("Я пока не знаю, как ответить. Попробуйте /start или команду помощи.")
