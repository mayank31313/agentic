import os

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_REMOVED
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from cndi.annotations import Bean
from cndi.annotations.events import OnEvent
from cndi.env import getContextEnvironment
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from telegram import Bot
from tinydb import TinyDB

from agentic.app.constants import CRON_UPDATE_EVENT
from agentic.app.scheduler.tools import CronSchedule
import logging

logger = logging.getLogger(__name__)


def execute_task(cron: CronSchedule, bot: Bot):
    agent = create_deep_agent(
        system_prompt=cron.subagent.system_prompt,
        name=cron.subagent.agent_name,
        backend=FilesystemBackend(root_dir="./workspace", virtual_mode=True),
        model=cron.subagent.model,
    )

    result = agent.invoke(dict(messages=cron.task)).get('messages')[-1]
    for content in filter(lambda x: x['type'] == 'text', result.content):
        print(content['text'])

    logger.info(result)

@OnEvent(CRON_UPDATE_EVENT)
def update_crons(action: str, cron: CronSchedule, scheduler: BackgroundScheduler, bot: Bot):
    try:
        job_id = str(cron.id)
        job = scheduler.get_job(job_id)
        if job:
            job.remove()
        if action != "DELETE":
            scheduler.add_job(execute_task, CronTrigger.from_crontab(cron.cron_expression), id=str(cron.id), kwargs=dict(cron=cron, bot=bot))
        logger.info(f"Cron Updated: {action} : {cron}")
    except Exception as e:
        logger.error(f"Failed to update schedule: {e}")

def job_listener(event):
    logger.info(f"Event {event} executed")

@Bean()
def getBankgroundScheduler(bot: Bot) -> BackgroundScheduler:
    time_zone = getContextEnvironment("cron.scheduler.timezone", "Europe/London")

    executors = {
        'default': {'type': 'threadpool', 'max_workers': 20},
        'processpool': ProcessPoolExecutor(max_workers=5)
    }

    with TinyDB(os.environ.get('CRON_SCHEDULE_FILENAME', "cron_schedules.json")) as db:
        crons = [CronSchedule.model_validate(row) for row in db.all()]
        scheduler = BackgroundScheduler()
        scheduler.configure(executors=executors, timezone=time_zone)
        scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_EXECUTED | EVENT_JOB_REMOVED )
        for cron in crons:
            scheduler.add_job(execute_task, CronTrigger.from_crontab(cron.cron_expression), kwargs=dict(cron=cron, bot=bot))

        scheduler.start()
    return scheduler