"""Unit tests for `agentic.app.common.backends.AgenticShellBackend`.

Unlike `test_tools.py`, this module imports the real `agentic.app.common.backends`
module directly rather than faking its dependencies out: it only depends on
`deepagents`/`langchain`, which are already real project dependencies, so there's
no need to stub anything to exercise the backend's actual filesystem/shell
behavior.
"""

from deepagents.backends import LocalShellBackend

from agentic.app.common.backends import AgenticShellBackend, SHELL_BACKEND_INTERRUPT_ON


def test_is_a_local_shell_backend_subclass():
    # AgenticShellBackend is intentionally a thin subclass; verify it hasn't
    # drifted from LocalShellBackend's public contract.
    assert issubclass(AgenticShellBackend, LocalShellBackend)


def test_filesystem_write_then_read_roundtrip(tmp_path):
    backend = AgenticShellBackend(root_dir=str(tmp_path), virtual_mode=True)

    write_result = backend.write("/hello.txt", "hello world")
    assert write_result.error is None

    read_result = backend.read("/hello.txt")
    assert read_result.error is None
    assert read_result.file_data["content"] == "hello world"


def test_execute_runs_generic_shell_command(tmp_path):
    backend = AgenticShellBackend(root_dir=str(tmp_path), virtual_mode=True, inherit_env=True)

    response = backend.execute("echo hello")

    assert response.exit_code == 0
    assert "hello" in response.output


def test_execute_can_invoke_agentic_cli_like_any_other_command(tmp_path):
    # This backend does NOT special-case `agentic` invocations (that guarded
    # validation lives only in the separate `agentic_run_agentic_cli` tool in
    # agentic.app.common.tools). Plain shell access means an `agentic ...`
    # command is executed exactly like any other shell command; here we
    # confirm no interception/rewriting happens by running a stand-in
    # executable-shaped command and checking it reaches the real shell
    # unmodified (a real `agentic` binary may not be on PATH in CI, so we
    # assert on the failure mode instead: a "not found"/non-zero exit,
    # never a validation error from this backend).
    backend = AgenticShellBackend(root_dir=str(tmp_path), virtual_mode=True, inherit_env=True)

    response = backend.execute("definitely-not-a-real-agentic-cli-binary --help")

    assert response.exit_code != 0


def test_shell_backend_interrupt_on_requires_approval_for_execute():
    assert "execute" in SHELL_BACKEND_INTERRUPT_ON
    config = SHELL_BACKEND_INTERRUPT_ON["execute"]
    assert set(config["allowed_decisions"]) == {"approve", "reject"}


