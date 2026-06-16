from aiogram import Bot, Dispatcher

from fleetops.config import AppConfig
from fleetops.interfaces.telegram.handlers import build_router
from fleetops.services.health_service import HealthService
from fleetops.services.snapshot_service import SnapshotService


async def run_bot(
    *,
    token: str,
    config: AppConfig,
    health_service: HealthService,
    snapshot_service: SnapshotService,
) -> None:
    bot = Bot(token=token)
    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(
            allowed_user_ids=set(config.telegram.allowed_user_ids),
            health_service=health_service,
            snapshot_service=snapshot_service,
        )
    )
    await dispatcher.start_polling(bot)

