from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


class TaskScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self.job_id = "strmthumbnail_job"

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def update_cron(self, cron_expr: str, callback) -> None:
        if not cron_expr:
            return
        trigger = CronTrigger.from_crontab(cron_expr)
        self.scheduler.add_job(
            callback,
            trigger=trigger,
            id=self.job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
