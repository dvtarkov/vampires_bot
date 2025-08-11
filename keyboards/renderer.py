# keyboards/renderer.py
import os
from typing import Tuple, List, Dict, Any, Iterable
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from aiogram.types import (
    InlineKeyboardMarkup, ReplyKeyboardMarkup,
    InlineKeyboardButton, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import load_config
from .spec import KeyboardSpec, RowOrName

_cfg = load_config()

class KeyboardRenderer:
    def __init__(self, template_root: str | None = None):
        self.template_root = template_root or _cfg.template_root
        self._env_cache: Dict[Tuple[str, str], Environment] = {}

    def _get_env(self, path: str) -> Environment:
        key = ("env", path)
        if key not in self._env_cache:
            self._env_cache[key] = Environment(loader=FileSystemLoader(path), autoescape=False)
        return self._env_cache[key]

    def _render_button_text(self, spec: KeyboardSpec, button_name: str, context: Dict[str, Any]) -> str:
        loc = (context.get("localization") or _cfg.default_localization).lower()
        localized_dir = os.path.join(self.template_root, loc, "keyboards", spec.name)
        global_dir    = os.path.join(self.template_root, "keyboards", spec.name)

        candidates = [button_name, f"{button_name}.j2", f"{button_name}.txt.j2"]

        if os.path.isdir(localized_dir):
            env = self._get_env(localized_dir)
            for c in candidates:
                try:
                    return env.get_template(c).render(**context)
                except TemplateNotFound:
                    pass

        if os.path.isdir(global_dir):
            env = self._get_env(global_dir)
            for c in candidates:
                try:
                    return env.get_template(c).render(**context)
                except TemplateNotFound:
                    pass

        return button_name.replace("_", " ").title()  # fallback

    # --- NEW: нормализация опций в явные ряды ---
    def _options_to_rows(self, options: List[RowOrName], max_in_row: int) -> List[List[str]]:
        rows: List[List[str]] = []
        pending: List[str] = []

        def flush_pending():
            nonlocal pending
            if not pending:
                return
            # разбиваем pending батчами max_in_row
            for i in range(0, len(pending), max_in_row):
                rows.append(pending[i:i+max_in_row])
            pending = []

        for item in options:
            if isinstance(item, list):
                flush_pending()
                # пустые списки игнорируем
                if item:
                    rows.append(item)
            else:
                pending.append(item)

        flush_pending()
        return rows

    def build(self, spec: KeyboardSpec, common_context: Dict[str, Any]) -> InlineKeyboardMarkup | ReplyKeyboardMarkup:
        ctx = {**common_context, **spec.context}

        # соберём уникальные имена для рендера текстов один раз
        def iter_names(opts: Iterable[RowOrName]) -> Iterable[str]:
            for it in opts:
                if isinstance(it, list):
                    for name in it:
                        yield name
                else:
                    yield it

        unique_names = list(dict.fromkeys(iter_names(spec.options)))
        text_map: Dict[str, str] = {}
        for name in unique_names:
            t = self._render_button_text(spec, name, ctx).strip() or name.replace("_", " ").title()
            text_map[name] = t

        rows = self._options_to_rows(spec.options, spec.params.max_in_row)

        if spec.type == "inline":
            builder = InlineKeyboardBuilder()
            for row in rows:
                buttons = [
                    InlineKeyboardButton(
                        text=text_map[name],
                        callback_data=f"{spec.name}_{name}"
                    )
                    for name in row
                ]
                builder.row(*buttons)
            markup = builder.as_markup()
            return markup

        # reply
        rbuilder = ReplyKeyboardBuilder()
        for row in rows:
            buttons = [KeyboardButton(text=text_map[name]) for name in row]
            rbuilder.row(*buttons)
        rmarkup = rbuilder.as_markup(
            resize_keyboard=spec.params.resize_keyboard,
            one_time_keyboard=spec.params.one_time_keyboard,
            is_persistent=spec.params.is_persistent,
            selective=spec.params.selective,
            input_field_placeholder=spec.params.input_field_placeholder,
        )
        return rmarkup
