"""Custom deepagents backend combining filesystem access with local shell execution.

`AgenticShellBackend` is a thin, intentionally minimal subclass of
`deepagents.backends.LocalShellBackend`: it inherits filesystem operations
(read/write/edit/ls/grep/glob) and shell command execution as-is, with no
special interception of `agentic` CLI invocations. Agents that get this
backend can run the `agentic` CLI (or anything else) through plain shell
access, but the validated/allowlisted `agentic_run_agentic_cli` tool (see
`agentic.app.common.tools`) remains the recommended, separately-gated way to
drive the Agentic CLI and is intentionally left untouched by this backend.

Security: see `LocalShellBackend`'s docstring for the full warning. This
backend is opt-in per agent (`AgentConfig.enable_shell_backend`) and should
always be paired with Human-in-the-Loop approval on its `execute` tool —
wiring for that lives in `agentic.app.agents.get_main_agent` and
`agentic.app.common.tools._create_sub_agent`, not here.
"""

import logging

from deepagents.backends import LocalShellBackend
from langchain.agents.middleware import InterruptOnConfig

logger = logging.getLogger(__name__)


class AgenticShellBackend(LocalShellBackend):
    """Filesystem + local shell backend for agents that opt in via config.

    Deliberately adds no behavior on top of `LocalShellBackend` — it exists
    as a distinctly named class so:

    - `resources/agentic.json` / `workspace/agents/<name>/instructions.md`
      configuration and code that wires backends can refer to a
      project-specific type rather than reaching for the raw `deepagents`
      class directly.
    - Any Agentic-specific hardening (e.g. output redaction, audit logging)
      can be added later in one place without touching call sites.
    """


# Always-required-approval HITL config for the shell backend's `execute` tool.
# Mounted whenever `AgentConfig.enable_shell_backend` is True — shell access is
# unrestricted (see `LocalShellBackend`'s security warning), so every call must
# go through human approval regardless of any other tool-approval config.
# Shared between `agentic.app.agents.get_main_agent` and
# `agentic.app.common.tools._create_sub_agent` (kept here, not in either of
# those modules, to avoid a circular import between them).
SHELL_BACKEND_INTERRUPT_ON = {
    "execute": InterruptOnConfig(
        allowed_decisions=["approve", "reject"],
        description=(
            "The agent wants to run a shell command via the AgenticShellBackend "
            "(unrestricted local shell execution, mounted at /shell/)."
        ),
    ),
}

__all__ = ["AgenticShellBackend", "SHELL_BACKEND_INTERRUPT_ON"]


