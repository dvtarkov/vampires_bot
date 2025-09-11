from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Union


def read_last_cycle_finished(path: Union[str, Path] = "last_cycle_finished.txt") -> Optional[datetime]:
    """
    Читает время завершения последнего цикла из файла и возвращает
    timezone-aware datetime в UTC. Если файл отсутствует, пустой или
    содержит некорректную дату — возвращает None.
    """
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None

    if not raw:
        return None

    # Основной формат — datetime.isoformat(), например: '2025-03-18T12:34:56+00:00'
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        # На всякий случай — поддержим 'Z' в конце: '...T12:34:56Z'
        if raw.endswith("Z"):
            try:
                dt = datetime.fromisoformat(raw[:-1])
                dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        else:
            return None

    # Если вдруг дата без таймзоны — считаем её UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)
