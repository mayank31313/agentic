import asyncio
import logging
import os

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_REMOVED
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from cndi.annotations import Bean
from cndi.annotations.events import OnEvent
from cndi.env import getContextEnvironment
from tinydb import TinyDB

from agentic import AgenticConfig
from agentic.app.agents import AgentRegistry
from agentic.app.common.tools import ToolsRegistry
from agentic.app.constants import CRON_UPDATE_EVENT
from agentic.app.scheduler.tools import CronSchedule

logger = logging.getLogger(__name__)


def job_listener(event):
    logger.info(f"Event {event} executed")


@Bean()
def getBankgroundScheduler(agent_registry: AgentRegistry) -> BackgroundScheduler:
    time_zone = getContextEnvironment("cron.scheduler.timezone", "Europe/London")

    executors = {
        "default": {"type": "threadpool", "max_workers": 20},
        "processpool": ProcessPoolExecutor(max_workers=5),
    }

    @OnEvent(CRON_UPDATE_EVENT)
    def update_crons(action: str, cron: CronSchedule, scheduler: BackgroundScheduler):
        try:
            job_id = str(cron.id)
            job = scheduler.get_job(job_id)
            if job:
                job.remove()
            if action != "DELETE":
                scheduler.add_job(
                    execute_task,
                    CronTrigger.from_crontab(cron.cron_expression),
                    id=str(cron.id),
                    kwargs=dict(cron=cron),
                )
            logger.info(f"Cron Updated: {action} : {cron}")
        except Exception as e:
            logger.error(f"Failed to update schedule: {e}")

    def execute_task(cron: CronSchedule):
        try:
            agent = agent_registry.get_agent(cron.subagent.agent_name)
        except KeyError as e:
            logger.error(str(e))
            return
        result = asyncio.run(agent.ainvoke(dict(messages=cron.task))).get("messages")
        logger.info(result)

    with TinyDB(os.environ.get("CRON_SCHEDULE_FILENAME", "cron_schedules.json")) as db:
        crons = [CronSchedule.model_validate(row) for row in db.all()]
        scheduler = BackgroundScheduler()
        scheduler.configure(executors=executors, timezone=time_zone)
        scheduler.add_listener(
            job_listener,
            EVENT_JOB_EXECUTED
            | EVENT_JOB_ERROR
            | EVENT_JOB_EXECUTED
            | EVENT_JOB_REMOVED,
        )
        for cron in crons:
            scheduler.add_job(
                execute_task,
                CronTrigger.from_crontab(cron.cron_expression),
                kwargs=dict(cron=cron),
            )

        scheduler.start()
    return scheduler
