import os
from typing import Any, Dict, Tuple, Optional
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from config import load_config
from keyboards.renderer import KeyboardRenderer
from keyboards.spec import KeyboardSpec

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

        reply_markup = kwargs.get("reply_markup")
        keyboard_spec = kwargs.get("keyboard")

        if keyboard_spec is not None:
            reply_markup = _keyboard_renderer.build(keyboard_spec, kwargs)

        message = kwargs.get("message")
        if message is not None and hasattr(message, "answer"):
            send_kwargs = {
                "parse_mode": "HTML",
                "disable_web_page_preview": kwargs.get("disable_web_page_preview", True),
            }

            # ВАЖНО: прикрепляем то, что построили (даже если в kwargs нет reply_markup)
            if reply_markup is not None:
                import logging
                logging.info("Sending with reply_markup=%s", type(reply_markup).__name__)
                send_kwargs["reply_markup"] = reply_markup

            # Если явно передали parse_mode/reply_parameters — они перекроют дефолты
            for k in ("reply_parameters", "parse_mode"):
                if k in kwargs:
                    send_kwargs[k] = kwargs[k]

            sent = await message.answer(rendered, **send_kwargs)
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
