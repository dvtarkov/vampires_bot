# screens/base.py (замените _render целиком)
import os
import logging
from typing import Any, Dict, Tuple, Optional
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from aiogram.exceptions import TelegramBadRequest

from config import load_config
from keyboards.renderer import KeyboardRenderer
from keyboards.spec import KeyboardSpec
from services.message_store import get_message, set_message, clear_message
from utils.render import content_hash
from aiogram import types

_config = load_config()
_keyboard_renderer = KeyboardRenderer()


def camel_to_snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i and (not name[i - 1].isupper()):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


class BaseScreen:
    template_root: str = _config.template_root
    _env_cache: Dict[Tuple[str, str], Environment] = {}

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        args, kwargs = await self._apply_stage(self._pre_render, *args, **kwargs)
        args, kwargs = await self._apply_stage(self._render, *args, **kwargs)
        args, kwargs = await self._apply_stage(self._post_render, *args, **kwargs)
        return kwargs.get("_result")

    async def _pre_render(self, *args: Any, **kwargs: Any) -> Optional[Any]:
        return None

    async def _render(self, *args: Any, **kwargs: Any) -> Optional[Any]:
        localization = kwargs.get("localization", _config.default_localization)
        class_snake = camel_to_snake(self.__class__.__name__)
        env = self._get_env(localization)

        candidates = [class_snake, f"{class_snake}.j2", f"{class_snake}.txt.j2"]
        template = None
        for name in candidates:
            try:
                template = env.get_template(name)
                break
            except TemplateNotFound:
                continue
        if template is None:
            raise FileNotFoundError(
                f"Template not found for {self.__class__.__name__} "
                f"in {self.template_root}/{localization}/ among {candidates}"
            )
        rendered = template.render(**kwargs)

        # Клавиатура (если задали спецификацию)
        reply_markup = kwargs.get("reply_markup")
        keyboard_spec: KeyboardSpec | None = kwargs.get("keyboard")
        if keyboard_spec is not None:
            reply_markup = _keyboard_renderer.build(keyboard_spec, kwargs)

        message: types.Message | None = kwargs.get("message")

        # -------- РЕЖИМЫ ОТПРАВКИ / РЕДАКТИРОВАНИЯ ----------
        render_kind: str = kwargs.get("render_kind", "main")  # "main" | "notice"
        force_new: bool = kwargs.get("force_new", False)
        no_store: bool = kwargs.get("no_store", False)
        persist_key: str = kwargs.get("persist_key", "main")
        max_age: int = int(kwargs.get("allow_edit_age_sec", 172800))  # 48h

        chat_id = kwargs.get("chat_id")
        if chat_id is None:
            if message is None:
                raise ValueError("chat_id или message обязательно")
            chat_id = message.chat.id

        send_kwargs = {
            "parse_mode": kwargs.get("parse_mode", "HTML"),
            "disable_web_page_preview": kwargs.get("disable_web_page_preview", True),
        }
        if reply_markup is not None:
            logging.info("Sending with reply_markup=%s", type(reply_markup).__name__)
            send_kwargs["reply_markup"] = reply_markup
        if "reply_parameters" in kwargs:
            send_kwargs["reply_parameters"] = kwargs["reply_parameters"]

        # Хэш для идемпотентности
        c_hash = content_hash(rendered, reply_markup)

        # Нотификация — всегда новое сообщение, не трогаем main
        if render_kind == "notice" or force_new:
            if message:
                sent = await message.answer(rendered, **send_kwargs)
            else:
                bot = message.bot if message else kwargs.get("bot")
                if bot is None:
                    raise ValueError("Нужен bot или message")
                sent = await bot.send_message(
                                chat_id=chat_id,
                                text=rendered,
                                **send_kwargs,
                            )
            if not no_store:
                set_message(chat_id, persist_key, render_kind, sent.message_id, c_hash)
            return {"rendered_text": rendered, "_result": sent, "reply_markup": reply_markup}

        # Попытка редактирования "main"
        stored = get_message(chat_id, persist_key, "main")
        logging.info(f"persist_key={persist_key}, stored={stored}")
        if stored:
            last_id, ts, prev_hash = stored
            # если контент не поменялся — ничего не делаем
            if prev_hash == c_hash:
                logging.info("Skip edit: content not changed (%s)", persist_key)
                return {"rendered_text": rendered, "_result": None, "reply_markup": reply_markup}

            age_ok = (ts is None) or ((__import__("time").time() - ts) <= max_age)
            if age_ok:
                try:
                    edited = await message.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=last_id,
                        text=rendered,
                        parse_mode=send_kwargs["parse_mode"],
                        disable_web_page_preview=send_kwargs["disable_web_page_preview"],
                        reply_markup=send_kwargs.get("reply_markup"),
                    )
                    set_message(chat_id, persist_key, "main", edited.message_id, c_hash)
                    return {"rendered_text": rendered, "_result": edited, "reply_markup": reply_markup}
                except TelegramBadRequest as e:
                    # Частые случаи: "message is not modified", "message to edit not found", "message can't be edited"
                    logging.warning("Edit failed (%s), fallback to send: %s", persist_key, e)

        # Если нечего редактировать или не вышло — отправляем новое и сохраняем
        sent = await message.answer(rendered, **send_kwargs)
        if not no_store:
            set_message(chat_id, persist_key, "main", sent.message_id, c_hash)
        return {"rendered_text": rendered, "_result": sent, "reply_markup": reply_markup}

    async def _post_render(self, *args: Any, **kwargs: Any) -> Optional[Any]:
        return None

    def _get_env(self, localization: str) -> Environment:
        key = (self.template_root, localization)
        env = self._env_cache.get(key)
        if env is None:
            folder = os.path.join(self.template_root, localization)
            env = Environment(loader=FileSystemLoader(folder), autoescape=False)
            self._env_cache[key] = env
        return env

    async def _apply_stage(self, stage, *args: Any, **kwargs: Any) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
        ret = await stage(*args, **kwargs)
        if ret is None:
            return args, kwargs
        if isinstance(ret, dict):
            kwargs.update(ret)
            return args, kwargs
        if isinstance(ret, tuple) and len(ret) == 2:
            new_args, new_kwargs = ret
            if not isinstance(new_args, tuple):
                new_args = tuple(new_args) if isinstance(new_args, (list, tuple)) else (new_args,)
            if not isinstance(new_kwargs, dict):
                raise TypeError("Stage returned tuple but second element is not a dict")
            return new_args, new_kwargs
        kwargs["_result"] = ret
        return args, kwargs
