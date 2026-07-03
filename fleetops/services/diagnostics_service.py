from fleetops.collectors.base import Collector


class DiagnosticsService:
    def __init__(self, collector: Collector) -> None:
        self.collector = collector

    async def get_services(self) -> str:
        return await self.collector.collect_services()

    async def get_journal(self) -> str:
        return await self.collector.collect_journal()

    async def get_ports(self) -> str:
        return await self.collector.collect_ports()

    async def get_docker(self) -> str:
        return await self.collector.collect_docker()

    async def get_mail(self) -> str:
        return await self.collector.collect_mail()

    async def get_mail_queue(self) -> str:
        return await self.collector.collect_mail_queue()

    async def get_mail_dns(self) -> str:
        return await self.collector.collect_mail_dns()

    async def get_mail_tls(self) -> str:
        return await self.collector.collect_mail_tls()

    async def get_mail_logs(self) -> str:
        return await self.collector.collect_mail_logs()

    async def get_mail_rejections(self) -> str:
        return await self.collector.collect_mail_rejections()

    async def get_mail_delivery(self) -> str:
        return await self.collector.collect_mail_delivery()

    async def get_mail_stats(self) -> str:
        return await self.collector.collect_mail_stats()

    async def get_mail_service_logs(self) -> str:
        return await self.collector.collect_mail_service_logs()

    async def get_greylist(self) -> str:
        return await self.collector.collect_greylist()

    async def get_top(self) -> str:
        return await self.collector.collect_top()

    async def get_processes(self) -> str:
        return await self.collector.collect_processes()

    async def get_reboots(self) -> str:
        return await self.collector.collect_reboots()

    async def get_updates(self) -> str:
        return await self.collector.collect_updates()

    async def get_security(self) -> str:
        return await self.collector.collect_security()

    async def get_docker_logs(self) -> str:
        return await self.collector.collect_docker_logs()

    async def get_audit(self) -> str:
        return await self.collector.collect_audit()
