from datetime import UTC, datetime

from aiogram import Bot, Dispatcher

from fleetops.config import AppConfig
from fleetops.interfaces.telegram.handlers import build_router
from fleetops.services.diagnostics_service import DiagnosticsService
from fleetops.services.health_service import HealthService
from fleetops.services.snapshot_service import SnapshotService


async def run_bot(
    *,
    token: str,
    config: AppConfig,
    demo_mode: bool,
    diagnostics_service: DiagnosticsService,
    health_service: HealthService,
    snapshot_service: SnapshotService,
) -> None:
    bot = Bot(token=token)
    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(
            config=config,
            demo_mode=demo_mode,
            allowed_user_ids=set(config.telegram.allowed_user_ids),
            started_at=datetime.now(UTC),
            diagnostics_service=diagnostics_service,
            health_service=health_service,
            snapshot_service=snapshot_service,
        )
    )
    await dispatcher.start_polling(bot)

