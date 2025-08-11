from aiogram import Router
from .start import router as start_router
from .universal import router as universal_router

router = Router()

# Сначала специфичные маршруты
router.include_router(start_router)

# Потом универсальные (фолбэк)
router.include_router(universal_router)
