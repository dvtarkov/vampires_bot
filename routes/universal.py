import logging
from aiogram import Router, F, types

router = Router()


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
