from pydantic import BaseModel


class HeartBeatConfig(BaseModel):
    """Configuration for the heartbeat mechanism."""

    interval_seconds: int = 60  # Interval in seconds for sending heartbeat signals
    enabled: bool = True  # Whether the heartbeat mechanism is enabled
