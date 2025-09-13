# admin_commands.py
import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Tuple
import html
from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select

from db.models import User
from db.session import get_session  # ваш общий фабричный get_session

log = logging.getLogger("admin_commands")
router = Router()

# ===== настройки путей к скриптам =====
# Можно задать абсолютные пути или относительные от корня проекта.
# При необходимости поменяйте на свои имена файлов.
SCRIPTS = {
    "export": "google_sheets_export.py",
    "import": "google_sheets_import.py",
    "answers": "send_ask_answers.py",
    "notify": "send_sheet_notifications.py",
    "sync_news": "sync_news_sheets.py",
    "sync_rituals": "sync_rituals.py",
}

# Опционально — рабочая директория проекта (чтобы относительные пути резолвились правильно)
PROJECT_CWD = Path(__file__).resolve().parent.parent  # при необходимости поднимитесь на уровень выше: .parent.parent

# ===== общие утилиты =====
async def _is_admin(tg_user_id: int) -> bool:
    async with get_session() as session:
        q = await session.execute(select(User).where(User.tg_id == tg_user_id))
        u = q.scalars().first()
        return bool(u and u.is_admin is True)

async def _run_script(script_path: Path, *args: str, timeout: int | None = None) -> Tuple[int, str, str]:
    """
    Запускает python-скрипт отдельным процессом и возвращает (returncode, stdout, stderr).
    """
    if not script_path.exists():
        return 127, "", f"Файл не найден: {script_path}"

    cmd = [sys.executable, str(script_path), *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(PROJECT_CWD),
        env=os.environ.copy(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return 124, "", f"Таймаут выполнения ({timeout}s)"

    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")

def _short(text: str, limit: int = 3500) -> str:
    """
    Режет длинный вывод, чтобы влезть в телеграм (лимит ~4096).
    Показываем хвост, потому что там обычно полезные сообщения.
    """
    text = text.strip()
    if len(text) <= limit:
        return text or "—"
    # оставим последние limit символов
    return "…(truncated)…\n" + text[-limit:]

async def _run_and_report(message: types.Message, title: str, script_key: str, *args: str, timeout: int | None = None):
    if not await _is_admin(message.from_user.id):
        await message.answer("Команда доступна только администраторам.")
        return

    await message.answer(f"⏳ {title}…")
    script_path = (PROJECT_CWD / SCRIPTS[script_key]).resolve()

    rc, out, err = await _run_script(script_path, *args, timeout=timeout)

    status = "✅ Успех" if rc == 0 else f"❌ Ошибка (rc={rc})"

    # ЭКРАНИРУЕМ логи для HTML
    out_escaped = html.escape(_short(out))
    err_escaped = html.escape(_short(err))

    body_parts = []
    if out.strip():
        body_parts.append(f"<b>stdout</b>:\n<pre>{out_escaped}</pre>")
    if err.strip():
        body_parts.append(f"<b>stderr</b>:\n<pre>{err_escaped}</pre>")

    body_text = "\n\n".join(body_parts) if body_parts else "Логи пусты."

    await message.answer(
        f"{status}\n<b>Скрипт:</b> <code>{html.escape(script_path.name)}</code>\n\n{body_text}",
        parse_mode="HTML",
    )
# =========================
# 1) /admin_export_models
# =========================
@router.message(Command("admin_export_models"))
async def admin_export_models(message: types.Message):
    await _run_and_report(
        message,
        title="Экспорт моделей в Google Sheets",
        script_key="export",
        timeout=None,  # можно выставить, например, 600
    )

# =========================
# 2) /admin_import_models
# =========================
@router.message(Command("admin_import_models"))
async def admin_import_models(message: types.Message):
    await _run_and_report(
        message,
        title="Импорт моделей из Google Sheets",
        script_key="import",
        timeout=None,
    )

# =========================
# 3) /admin_send_answers
# =========================
@router.message(Command("admin_send_answers"))
async def admin_send_answers(message: types.Message):
    await _run_and_report(
        message,
        title="Рассылка ответов из ask_and_answer",
        script_key="answers",
        timeout=None,
    )

# =========================
# 4) /admin_notify_users
# =========================
@router.message(Command("admin_notify_users"))
async def admin_notify_users(message: types.Message):
    await _run_and_report(
        message,
        title="Рассылка уведомлений из notify_users",
        script_key="notify",
        timeout=None,
    )

# =========================
# 5) /admin_sync_news
# =========================
@router.message(Command("admin_sync_news"))
async def admin_sync_news(message: types.Message):
    await _run_and_report(
        message,
        title="Синхронизация новостей (news_to_print → news, RAW → news, DONE/notify)",
        script_key="sync_news",
        timeout=None,
    )

# =========================
# 6) /admin_sync_rituals
# =========================
@router.message(Command("admin_sync_rituals"))
async def admin_sync_rituals(message: types.Message):
    await _run_and_report(
        message,
        title="Обработка RESOLVED ритуалов: перевод PENDING → DONE и уведомления",
        script_key="sync_rituals",
        timeout=None,
    )