#!/usr/bin/env python3
"""
Helper wrapper for the `agentic` CLI, invoked via `uv run agentic`.

Purpose: give an agent a single, predictable entry point that captures
stdout, stderr, and the exit code *separately* (instead of merged shell
output), and returns them as structured JSON. This makes it far easier for
an agent to apply the error-recovery table in SKILL.md programmatically
instead of eyeballing raw terminal text.

Usage:
    python scripts/run_agentic.py <agentic-subcommand-and-args...>
    python scripts/run_agentic.py -- config get telegram.bot_token
    python scripts/run_agentic.py --cwd /path/to/project -- agents list
    python scripts/run_agentic.py --json -- config schema

Examples:
    python scripts/run_agentic.py -- mcp list
    python scripts/run_agentic.py -- config set telegram.bot_token --set telegram.bot_token=123:ABC
    python scripts/run_agentic.py --timeout 10 -- run

Output (always JSON on stdout, regardless of --json flag on the wrapped
command):
    {
        "command": ["uv", "run", "agentic", "config", "get", "telegram.bot_token"],
        "cwd": "/path/to/project",
        "exit_code": 0,
        "success": true,
        "stdout": "...",
        "stderr": "",
        "stdout_json": {...} | null,   # parsed if stdout is valid JSON, else null
        "timed_out": false
    }

Exit code of this wrapper itself mirrors the wrapped command's exit code,
so it's safe to check `$?` after calling it directly, in addition to
parsing the JSON body.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_agentic(args: list[str], cwd: str | None, timeout: float | None) -> dict:
    command = ["uv", "run", "agentic", *args]

    result_payload = {
        "command": command,
        "cwd": cwd or str(Path.cwd()),
        "exit_code": None,
        "success": False,
        "stdout": "",
        "stderr": "",
        "stdout_json": None,
        "timed_out": False,
    }

    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result_payload["exit_code"] = proc.returncode
        result_payload["success"] = proc.returncode == 0
        result_payload["stdout"] = proc.stdout
        result_payload["stderr"] = proc.stderr

        # Best-effort JSON parse of stdout, since most `agentic config`/
        # `agentic agents list` output is JSON. Silently ignore parse
        # failures — plain-text output (e.g. from `agentic run`) is fine.
        stripped = proc.stdout.strip()
        if stripped:
            try:
                result_payload["stdout_json"] = json.loads(stripped)
            except json.JSONDecodeError:
                pass

    except subprocess.TimeoutExpired as e:
        result_payload["timed_out"] = True
        result_payload["exit_code"] = None
        result_payload["success"] = False
        result_payload["stdout"] = e.stdout or ""
        result_payload["stderr"] = (e.stderr or "") + (
            f"\n[wrapper] Command timed out after {timeout}s. "
            "If this was `agentic run` (a blocking server), that's "
            "expected — re-run in the background instead of via this "
            "wrapper, or increase --timeout."
        )

    except FileNotFoundError:
        result_payload["exit_code"] = 127
        result_payload["success"] = False
        result_payload["stderr"] = (
            "[wrapper] 'uv' was not found on PATH. Install uv, or run the "
            "underlying command manually to confirm the environment."
        )

    return result_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an `agentic` CLI command via `uv run agentic` with structured JSON output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Directory to run the command from (default: current directory). "
        "Should usually be the project root containing agentic.json and pyproject.toml.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds (default: 30). Use a short timeout for anything "
        "other than 'agentic run', which blocks indefinitely by design.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the wrapper's JSON output (default is compact).",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Everything after this is passed through to `agentic` as-is. "
        "Use '--' before it if any of your args start with '-'.",
    )

    parsed = parser.parse_args()

    agentic_args = parsed.args
    if agentic_args and agentic_args[0] == "--":
        agentic_args = agentic_args[1:]

    if not agentic_args:
        parser.print_help()
        return 2

    payload = run_agentic(agentic_args, cwd=parsed.cwd, timeout=parsed.timeout)

    indent = 2 if parsed.pretty else None
    print(json.dumps(payload, indent=indent))

    # Mirror the wrapped command's exit code so `$?` works as expected too.
    if payload["timed_out"]:
        return 124  # conventional shell timeout exit code
    return payload["exit_code"] if payload["exit_code"] is not None else 1


if __name__ == "__main__":
    sys.exit(main())
