import logging
import os
from uuid import UUID, uuid4

from cndi.annotations import Autowired
from cndi.annotations.events import EventBus
from cndi.env import getContextEnvironment
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from tinydb import Query, TinyDB

from agentic.app.common.tools import ToolsRegistry
from agentic.app.constants import CRON_UPDATE_EVENT, TELEGRAM_BOT_DEFAULT_CHAT_ID

logger = logging.getLogger(__name__)


class SubAgentConfig(BaseModel):
    """Serializable description of how to build a subagent.
    Decoupled from any specific agent implementation — the cron
    executor only needs this data, never a live agent object."""

    agent_name: str = Field(
        ...,
        description="Registered agent name, use agentic cli to list agents and identify the exact agent name",
    )


class Delivery(BaseModel):
    to: list[str] = Field(description="list of channel ids to send the message to")
    channel: str = Field(default="telegram", description="name of the channel")
    mode: str = Field(default="announce", description="mode of communication")


class CronSettings(BaseModel):
    task: str = Field(..., description="Task user has given to complete")
    cron_expression: str = Field(
        ...,
        description="The Cron expression string (e.g., '0 9 * * *' for every day at 9 AM).",
    )
    name: str = Field(
        description="The name of the schedule, if user does not specify agent to use a meaningful name."
    )


class CronSchedule(CronSettings):
    id: UUID = Field(
        default_factory=uuid4, description="Unique identifier for the cron job."
    )
    delivery: Delivery = Field(description="Delivery config to use for response")
    subagent: SubAgentConfig = Field(
        ...,
        description="Config describing which subagent to invoke and how to build it — never a live instance.",
    )


def get_cron_tools(event_bus: EventBus):
    @tool
    def delete_cron_tool(name: str) -> str:
        """
        Delete the cron job and schedule with cronjob name from the CronScheduleAgent name attribute, If name is unsure call list cron tool to validate
        """
        with TinyDB(
            os.environ.get("CRON_SCHEDULE_FILENAME", "cron_schedules.json")
        ) as db:
            cron = db.get(Query().name == name)
            if cron:
                db.remove(Query().name == name)
                event_bus.publish(
                    CRON_UPDATE_EVENT,
                    data=dict(action="DELETE", cron=CronSchedule.model_validate(cron)),
                )
                return f"Cron Job with name={name} deleted successfully"
            else:
                return f"Could not find Cron Job with name={name}, If you still want to delete a cron job better to valid the name from `list_cron` tool"

    @tool
    def create_cron_tool(
        cron_settings: CronSettings, sub_agent_config: SubAgentConfig
    ) -> str:
        """
        Create a cron job and schedule at the specified time. The cron_settings should be a CronScheduleAgent object containing the task and cron_expression.
        """
        try:
            with TinyDB(
                os.environ.get("CRON_SCHEDULE_FILENAME", "cron_schedules.json")
            ) as db:
                cron = CronSchedule(
                    **cron_settings.model_dump(mode="json"),
                    subagent=sub_agent_config,
                    delivery=Delivery(
                        to=[getContextEnvironment(TELEGRAM_BOT_DEFAULT_CHAT_ID)]
                    ),
                )
                db.insert(cron.model_dump(mode="json"))

                event_bus.publish(
                    CRON_UPDATE_EVENT, data=dict(action="UPDATE", cron=cron)
                )

                return f"Cron job successfully created with name '{cron_settings.name}' with cron expression '{cron_settings.cron_expression}' and message '{cron_settings.task}'."
        except Exception as e:
            logging.error(f"Error scheduling job: {e}")
            return f"Error: {e!s}"

    @tool
    def list_cron_tool() -> list[CronSchedule]:
        """List all scheduled cron jobs. Call this tool to see the current cron jobs and their settings."""
        try:
            with TinyDB(
                os.environ.get("CRON_SCHEDULE_FILENAME", "cron_schedules.json")
            ) as db:
                crons = [CronSchedule.model_validate(row) for row in db.all()]
                logger.info(crons)
                if crons.__len__() == 0:
                    return "No cron jobs scheduled."

                return crons
        except Exception as e:
            logging.error(f"Error listing cron schedules: {e}")
            return f"Error: {e!s}"

    @tool
    def update_cron_tool(
        name: str, cron_settings: CronSettings, sub_agent_config: SubAgentConfig
    ) -> str:
        """Update existing cron job with new settings. The cron_settings should be a CronScheduleAgent object containing the name, task and cron_expression."""
        try:
            with TinyDB(
                os.environ.get("CRON_SCHEDULE_FILENAME", "cron_schedules.json")
            ) as db:
                Schedule = Query()
                result = db.get(Schedule.name == name)
                schedule = CronSchedule.model_validate(result) if result else None

                if schedule:
                    cron = CronSchedule(
                        **cron_settings.model_dump(mode="json"),
                        subagent=sub_agent_config,
                        id=schedule.id,
                        delivery=schedule.delivery,
                    )
                    db.update(cron.model_dump(mode="json"), Schedule.name == name)
                    event_bus.publish(
                        CRON_UPDATE_EVENT, data=dict(action="UPDATE", cron=cron)
                    )
                    return f"Cron job '{name}' updated successfully with cron expression '{cron_settings.cron_expression}' and task '{cron_settings.task}'."
                else:
                    return f"No cron job found with the name '{name}'."
        except Exception as e:
            logging.error(f"Error updating cron schedule: {e}")
            return f"Error: {e!s}"

    return [create_cron_tool, list_cron_tool, update_cron_tool, delete_cron_tool]


@Autowired()
def register_cron_tools(tools_registry: ToolsRegistry, event_bus: EventBus):
    cron_tools = get_cron_tools(event_bus)
    for tool in cron_tools:
        tools_registry.register_tool(tool.name, tool)
