from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from fleetops.interfaces.telegram.formatter import format_health
from fleetops.services.health_service import HealthService
from fleetops.services.snapshot_service import SnapshotService


def build_router(
    *,
    allowed_user_ids: set[int],
    health_service: HealthService,
    snapshot_service: SnapshotService,
) -> Router:
    router = Router()

    def is_allowed(message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in allowed_user_ids

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer("FleetOps is ready. Use /health or /snapshot.")

    @router.message(Command("health"))
    async def health(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        result = await health_service.get_health()
        await message.answer(format_health(result), parse_mode="HTML")

    @router.message(Command("snapshot"))
    async def snapshot(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        path = await snapshot_service.create_snapshot()
        await message.answer_document(FSInputFile(path))

    return router

