from aiogram import Router
from .start import router as start_router
from .universal import router as universal_router
from .admin_set_owner import router as set_owner_router
router = Router()
router.include_router(set_owner_router)
# Сначала специфичные маршруты
router.include_router(start_router)

# Потом универсальные (фолбэк)
router.include_router(universal_router)

