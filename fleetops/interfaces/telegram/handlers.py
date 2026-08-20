from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from fleetops.config import AppConfig
from fleetops.interfaces.telegram.formatter import (
    format_audit,
    format_audit_detail,
    format_check_detail,
    format_docker,
    format_docker_deep,
    format_docker_logs,
    format_greylist,
    format_greylist_detail,
    format_health,
    format_incident,
    format_journal,
    format_mail,
    format_mail_delivery,
    format_mail_dns,
    format_mail_logs,
    format_mail_queue,
    format_mail_rejections,
    format_mail_search,
    format_mail_service_logs,
    format_mail_stats,
    format_mail_tls,
    format_ports,
    format_ports_detail,
    format_processes,
    format_reboots,
    format_security,
    format_services,
    format_services_detail,
    format_status,
    format_top,
    format_updates,
)
from fleetops.interfaces.telegram.messages import split_message
from fleetops.services.diagnostics_service import DiagnosticsService
from fleetops.services.health_service import HealthService
from fleetops.services.snapshot_service import SnapshotService


def build_router(
    *,
    config: AppConfig,
    demo_mode: bool,
    allowed_user_ids: set[int],
    started_at: datetime,
    diagnostics_service: DiagnosticsService,
    health_service: HealthService,
    snapshot_service: SnapshotService,
) -> Router:
    router = Router()

    def is_allowed_user(user_id: int | None) -> bool:
        return user_id is not None and user_id in allowed_user_ids

    def is_allowed(message: Message) -> bool:
        return message.from_user is not None and is_allowed_user(message.from_user.id)

    def command_tail(message: Message) -> str:
        text = message.text or ""
        parts = text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    def parse_since_arg(message: Message) -> str | None:
        tail = command_tail(message)
        return tail or None

    def parse_search_args(message: Message) -> tuple[str, str | None]:
        parts = command_tail(message).split()
        if not parts:
            return "", None
        since = None
        if len(parts) > 1 and parts[-1][-1:].lower() in {"m", "h", "d"}:
            since = parts[-1]
            parts = parts[:-1]
        return " ".join(parts), since

    def details_keyboard(target: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔎 Details", callback_data=f"details:{target}")]
            ]
        )

    def mail_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🧭 DNS", callback_data="mail:dns"),
                    InlineKeyboardButton(text="🔐 TLS", callback_data="mail:tls"),
                ],
                [
                    InlineKeyboardButton(text="📨 Logs", callback_data="mail:logs"),
                    InlineKeyboardButton(text="📊 Stats", callback_data="mail:stats"),
                ],
                [
                    InlineKeyboardButton(text="⛔ Rejects", callback_data="mail:rejects"),
                    InlineKeyboardButton(text="✅ Delivery", callback_data="mail:delivery"),
                ],
                [
                    InlineKeyboardButton(text="📬 Queue", callback_data="mail:queue"),
                    InlineKeyboardButton(text="🩶 Greylist", callback_data="mail:greylist"),
                ],
            ]
        )

    async def answer_chunks(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk)

    async def answer_check_detail(message: Message, check_name: str) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        result = await health_service.get_health()
        check = next((item for item in result.checks if item.name == check_name), None)
        if check is None:
            await message.answer(f"Check not found: {check_name}")
            return
        await message.answer(format_check_detail(check))

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer("FleetOps is ready. Use /health, /snapshot, /status, or /help.")

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied. Use /whoami to get your numeric Telegram ID.")
            return
        await message.answer(
            "\n".join(
                [
                    "FleetOps commands",
                    "",
                    "/health - collect current server health",
                    "/load - show load details",
                    "/memory - show memory details",
                    "/disk - show disk details",
                    "/systemd - show failed systemd units",
                    "/services - summarize running/failed services",
                    "/journal - show recent warning/error journal lines",
                    "/ports - show listening TCP/UDP sockets",
                    "/docker - show Docker containers and disk usage",
                    "/dockerdeep - show container health, restarts, resources, and disk usage",
                    "/dockerlogs [container] - show bounded logs for selected/running containers",
                    "/mail - show common mail service status",
                    "/maildns - show mail DNS records",
                    "/mailtls - show mail TLS certificate details",
                    "/maillogs [1h|24h|7d] - show parsed send/reject/defer mail flow",
                    "/mailstats [1h|24h|7d] - show aggregate mail flow statistics",
                    "/mailrejects [1h|24h|7d] - show rejected and greylisted mail events",
                    "/maildelivery [1h|24h|7d] - show sent/deferred/bounced mail events",
                    "/mailsearch <text> [1h|24h|7d] - search parsed mail events",
                    "/mailfrom <email/domain> [1h|24h|7d] - search by sender",
                    "/mailto <email/domain> [1h|24h|7d] - search by recipient",
                    "/mailip <ip> [1h|24h|7d] - search by client/relay IP",
                    "/maildomain <domain> [1h|24h|7d] - search by sender/recipient domain",
                    "/mailservice - show bounded mail service lifecycle logs",
                    "/greylist - show postgrey statistics and recent events",
                    "/queue - show mail queue summary",
                    "/top - show top snapshot",
                    "/processes - show top CPU/memory processes",
                    "/reboots - show uptime and reboot history",
                    "/updates - show package update hints",
                    "/security - show sessions, logins, firewall/security services",
                    "/audit - run read-only security and mail audit",
                    "/incident [1h|24h|7d] - build a compact incident report",
                    "/snapshot - create a redacted diagnostic snapshot",
                    "/status - show bot/runtime status",
                    "/whoami - show your numeric Telegram ID",
                    "/help - show this help",
                ]
            )
        )

    @router.message(Command("whoami"))
    async def whoami(message: Message) -> None:
        if message.from_user is None:
            await message.answer("Telegram user ID is unavailable.")
            return
        await message.answer(f"Your Telegram user ID: {message.from_user.id}")

    @router.message(Command("status"))
    async def status(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            format_status(
                hostname=config.host.hostname,
                host_id=config.host.id,
                demo_mode=demo_mode,
                allowed_user_count=len(allowed_user_ids),
                started_at=started_at,
            )
        )

    @router.message(Command("health"))
    async def health(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        result = await health_service.get_health()
        await message.answer(format_health(result), parse_mode="HTML")

    @router.message(Command("load"))
    async def load(message: Message) -> None:
        await answer_check_detail(message, "load")

    @router.message(Command("memory"))
    async def memory(message: Message) -> None:
        await answer_check_detail(message, "memory")

    @router.message(Command("disk"))
    async def disk(message: Message) -> None:
        await answer_check_detail(message, "disk")

    @router.message(Command("systemd"))
    async def systemd(message: Message) -> None:
        await answer_check_detail(message, "systemd")

    @router.message(Command("services"))
    async def services(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            format_services(await diagnostics_service.get_services()),
            reply_markup=details_keyboard("services"),
        )

    @router.message(Command("journal"))
    async def journal(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(format_journal(await diagnostics_service.get_journal()))

    @router.message(Command("ports"))
    async def ports(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            format_ports(await diagnostics_service.get_ports()),
            reply_markup=details_keyboard("ports"),
        )

    @router.message(Command("docker"))
    async def docker(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_docker(await diagnostics_service.get_docker()))

    @router.message(Command("dockerdeep"))
    async def dockerdeep(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(
            message,
            format_docker_deep(await diagnostics_service.get_docker_deep()),
        )

    @router.message(Command("dockerlogs"))
    async def dockerlogs(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        container = command_tail(message) or None
        try:
            raw = await diagnostics_service.get_docker_logs(container)
        except ValueError as exc:
            await message.answer(f"Bad container name: {exc}")
            return
        await answer_chunks(message, format_docker_logs(raw))

    @router.message(Command("mail"))
    async def mail(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            format_mail(await diagnostics_service.get_mail()),
            reply_markup=mail_keyboard(),
        )

    @router.message(Command("maildns"))
    async def maildns(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_mail_dns(await diagnostics_service.get_mail_dns()))

    @router.message(Command("mailtls"))
    async def mailtls(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_mail_tls(await diagnostics_service.get_mail_tls()))

    @router.message(Command("maillogs"))
    async def maillogs(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        since = parse_since_arg(message)
        try:
            raw = await diagnostics_service.get_mail_logs(since)
        except ValueError as exc:
            await message.answer(f"Bad time window: {exc}")
            return
        await answer_chunks(message, format_mail_logs(raw))

    @router.message(Command("mailstats"))
    async def mailstats(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        since = parse_since_arg(message)
        try:
            raw = await diagnostics_service.get_mail_stats(since)
        except ValueError as exc:
            await message.answer(f"Bad time window: {exc}")
            return
        await answer_chunks(message, format_mail_stats(raw))

    @router.message(Command("mailrejects"))
    async def mailrejects(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        since = parse_since_arg(message)
        try:
            raw = await diagnostics_service.get_mail_rejections(since)
        except ValueError as exc:
            await message.answer(f"Bad time window: {exc}")
            return
        await answer_chunks(
            message,
            format_mail_rejections(raw),
        )

    @router.message(Command("maildelivery"))
    async def maildelivery(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        since = parse_since_arg(message)
        try:
            raw = await diagnostics_service.get_mail_delivery(since)
        except ValueError as exc:
            await message.answer(f"Bad time window: {exc}")
            return
        await answer_chunks(
            message,
            format_mail_delivery(raw),
        )

    async def answer_mail_search(message: Message, mode: str) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        query, since = parse_search_args(message)
        if not query:
            await message.answer("Usage: /mailsearch <text> [1h|24h|7d]")
            return
        try:
            raw = await diagnostics_service.get_mail_search(
                mode=mode,
                query=query,
                since=since,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await answer_chunks(message, format_mail_search(raw, mode=mode, query=query, since=since))

    @router.message(Command("mailsearch"))
    async def mailsearch(message: Message) -> None:
        await answer_mail_search(message, "any")

    @router.message(Command("mailfrom"))
    async def mailfrom(message: Message) -> None:
        await answer_mail_search(message, "from")

    @router.message(Command("mailto"))
    async def mailto(message: Message) -> None:
        await answer_mail_search(message, "to")

    @router.message(Command("mailip"))
    async def mailip(message: Message) -> None:
        await answer_mail_search(message, "ip")

    @router.message(Command("maildomain"))
    async def maildomain(message: Message) -> None:
        await answer_mail_search(message, "domain")

    @router.message(Command("mailservice"))
    async def mailservice(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(
            message,
            format_mail_service_logs(await diagnostics_service.get_mail_service_logs()),
        )

    @router.message(Command("greylist"))
    async def greylist(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            format_greylist(await diagnostics_service.get_greylist()),
            reply_markup=details_keyboard("greylist"),
        )

    @router.message(Command("queue"))
    async def queue(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(format_mail_queue(await diagnostics_service.get_mail_queue()))

    @router.message(Command("top"))
    async def top(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_top(await diagnostics_service.get_top()))

    @router.message(Command("processes"))
    async def processes(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_processes(await diagnostics_service.get_processes()))

    @router.message(Command("reboots"))
    async def reboots(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_reboots(await diagnostics_service.get_reboots()))

    @router.message(Command("updates"))
    async def updates(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_updates(await diagnostics_service.get_updates()))

    @router.message(Command("security"))
    async def security(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await answer_chunks(message, format_security(await diagnostics_service.get_security()))

    @router.message(Command("audit"))
    async def audit(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        await message.answer(
            format_audit(await diagnostics_service.get_audit()),
            reply_markup=details_keyboard("audit"),
        )

    @router.message(Command("incident"))
    async def incident(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        since = parse_since_arg(message) or "24h"
        try:
            raw = await diagnostics_service.get_incident(since)
        except ValueError as exc:
            await message.answer(f"Bad time window: {exc}")
            return
        await answer_chunks(message, format_incident(raw))

    @router.callback_query(F.data == "details:services")
    async def services_details(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_services_detail(await diagnostics_service.get_services()),
        )

    @router.callback_query(F.data == "details:ports")
    async def ports_details(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_ports_detail(await diagnostics_service.get_ports()),
        )

    @router.callback_query(F.data == "details:audit")
    async def audit_details(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_audit_detail(await diagnostics_service.get_audit()),
        )

    @router.callback_query(F.data == "details:greylist")
    async def greylist_details(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_greylist_detail(await diagnostics_service.get_greylist()),
        )

    @router.callback_query(F.data == "mail:dns")
    async def mail_dns_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_mail_dns(await diagnostics_service.get_mail_dns()),
        )

    @router.callback_query(F.data == "mail:tls")
    async def mail_tls_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_mail_tls(await diagnostics_service.get_mail_tls()),
        )

    @router.callback_query(F.data == "mail:logs")
    async def mail_logs_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_mail_logs(await diagnostics_service.get_mail_logs()),
        )

    @router.callback_query(F.data == "mail:queue")
    async def mail_queue_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_mail_queue(await diagnostics_service.get_mail_queue()),
        )

    @router.callback_query(F.data == "mail:stats")
    async def mail_stats_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_mail_stats(await diagnostics_service.get_mail_stats()),
        )

    @router.callback_query(F.data == "mail:rejects")
    async def mail_rejects_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_mail_rejections(await diagnostics_service.get_mail_rejections()),
        )

    @router.callback_query(F.data == "mail:delivery")
    async def mail_delivery_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await answer_chunks(
            callback.message,
            format_mail_delivery(await diagnostics_service.get_mail_delivery()),
        )

    @router.callback_query(F.data == "mail:greylist")
    async def mail_greylist_callback(callback: CallbackQuery) -> None:
        if callback.message is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        if not is_allowed_user(callback.from_user.id):
            await callback.answer("Access denied.", show_alert=True)
            return
        await callback.answer()
        await callback.message.answer(
            format_greylist(await diagnostics_service.get_greylist()),
            reply_markup=details_keyboard("greylist"),
        )

    @router.message(Command("snapshot"))
    async def snapshot(message: Message) -> None:
        if not is_allowed(message):
            await message.answer("Access denied.")
            return
        path = await snapshot_service.create_snapshot()
        await message.answer_document(FSInputFile(path))

    return router

