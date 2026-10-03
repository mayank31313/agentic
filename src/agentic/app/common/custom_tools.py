"""Agent-authored custom tools ("agent writes its own tools").

This module implements the mechanism described in the project's dynamic
tool planning discussion: an agent can author a brand-new tool — either a
sandboxed Python script or a Dockerized script — via the `create_custom_tool`
tool exposed in `agentic.app.common.tools`. Every custom tool is:

1. Written to disk under `<workspace>/custom_tools/<name>/` (never under
   `src/`), so agent-authored code never touches the app's own source tree.
2. Statically checked (Python kind only) against an import/name allow-list
   before being accepted — a first line of defense, not a full sandbox.
3. Executed out-of-process (subprocess for Python, `docker run` for Docker),
   never via in-process `exec`/`eval`.
4. Gated behind human approval on *every* call until a human explicitly
   promotes it via `agentic tools custom approve <name>` (see
   `AgenticBot.initialise_agent` in `agentic.app.bot`, which always treats
   an unapproved custom tool as requiring approval regardless of the
   calling agent's own `tools` config).

None of this is a substitute for real OS-level sandboxing (seccomp,
gVisor, a locked-down docker daemon, etc.) — it is a set of speed bumps
appropriate for a human-in-the-loop assistant, not a multi-tenant
untrusted-code platform.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Static analysis for the Python kind. Deliberately conservative: this is a
# first line of defense, applied *before* a human ever sees/approves the
# code, not a claim of full sandboxing.
# --------------------------------------------------------------------------

ALLOWED_IMPORTS = frozenset(
    {
        "json",
        "math",
        "re",
        "datetime",
        "itertools",
        "statistics",
        "textwrap",
        "typing",
        "decimal",
        "collections",
        "string",
        "random",
        "uuid",
        "dataclasses",
        "enum",
        "functools",
    }
)

FORBIDDEN_CALL_NAMES = frozenset(
    {"eval", "exec", "compile", "__import__", "open", "input", "exit", "quit"}
)

FORBIDDEN_ATTR_ROOTS = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "importlib",
        "ctypes",
        "ftplib",
        "http",
        "urllib",
        "requests",
    }
)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


def validate_python_source(source: str) -> list[str]:
    """Statically validate agent-submitted Python source for a custom tool.

    Returns a list of human-readable violations; an empty list means the
    source passed the allow-list checks (still not a guarantee of safety —
    see module docstring).
    """
    violations: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"SyntaxError: {e}"]

    has_run_function = any(
        isinstance(node, ast.FunctionDef) and node.name == "run"
        for node in tree.body
    )
    if not has_run_function:
        violations.append(
            "Source must define a top-level function named `run(**kwargs)`."
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            for name in names:
                root = name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    violations.append(
                        f"Import of '{name}' is not allowed. Allowed modules: "
                        f"{', '.join(sorted(ALLOWED_IMPORTS))}."
                    )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALL_NAMES:
                violations.append(f"Call to '{func.id}(...)' is not allowed.")
        elif isinstance(node, ast.Attribute):
            value = node.value
            if isinstance(value, ast.Name) and value.id in FORBIDDEN_ATTR_ROOTS:
                violations.append(
                    f"Access to '{value.id}.{node.attr}' is not allowed."
                )

    return violations


# --------------------------------------------------------------------------
# Spec model
# --------------------------------------------------------------------------

_ARG_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
    # Common aliases an authoring agent (or human) may reach for instead of
    # the canonical JSON-Schema-ish names above. Accepted explicitly rather
    # than silently falling back to `str` for anything unrecognized (see
    # `_validate_tool_args`), which previously caused e.g. a declared "int"
    # argument to actually be typed/coerced as `str` at call time.
    "int": int,
    "str": str,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
}


def _validate_tool_args(tool_args: dict[str, str]) -> None:
    """Raise ``ValueError`` if any declared arg type isn't recognized.

    `_build_args_model` previously used ``_ARG_TYPES.get(type_name, str)``,
    which silently defaulted an unrecognized type name (e.g. the ``"int"``/
    ``"integer"`` mismatch) to ``str``. That meant a numeric argument could
    be silently typed/coerced as a string, only surfacing much later as a
    confusing ``TypeError`` inside the agent-authored tool body (e.g.
    ``'<' not supported between instances of 'str' and 'int'``). Validating
    eagerly, at tool creation/update time, fails fast with an actionable
    message instead.
    """
    unknown = {name: t for name, t in tool_args.items() if t not in _ARG_TYPES}
    if unknown:
        raise ValueError(
            "Unknown tool_args type(s): "
            + ", ".join(f"{name}={t!r}" for name, t in unknown.items())
            + f". Allowed types: {', '.join(sorted(_ARG_TYPES))}."
        )


class CustomToolSpec(BaseModel):
    name: str = Field(description="snake_case tool name, unique across custom tools")
    description: str = Field(description="What the tool does; shown to the LLM")
    kind: Literal["python", "docker"]
    tool_args: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of argument name -> type (string|integer|number|boolean|array|object)",
    )
    approved: bool = Field(
        default=False,
        description="Whether a human has reviewed and promoted this tool out of the mandatory per-call approval gate.",
    )
    approval_text: str | None = Field(default=None)
    network_access: bool = Field(
        default=False, description="Docker kind only: whether the container may access the network."
    )
    timeout_seconds: int = Field(default=30)
    created_by: str | None = Field(default=None)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_by: str | None = Field(default=None)
    updated_at: str | None = Field(default=None)


def _build_args_model(name: str, tool_args: dict[str, str]):
    fields = {}
    for arg_name, type_name in tool_args.items():
        py_type = _ARG_TYPES.get(type_name, str)
        fields[arg_name] = (py_type, Field(default=... if True else None))
    # Everything is required by default; callers wanting optional args can
    # model that with a dedicated "object"/dict argument instead.
    fields = {k: (v[0], Field(...)) for k, v in fields.items()}
    return create_model(f"{name}_Args", **fields)  # type: ignore[call-overload]


_TOOL_HARNESS_TEMPLATE = '''"""Auto-generated by Agentic's custom tool authoring mechanism.

This file was authored by an agent (via the `create_custom_tool` tool) and
reviewed by a human before being registered. Do not hand-edit without
re-running `agentic tools custom` validation.
"""
import json
import sys

{user_source}

if __name__ == "__main__":
    raw = sys.stdin.read()
    kwargs = json.loads(raw) if raw.strip() else {{}}
    try:
        result = run(**kwargs)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
        print(json.dumps({{"error": str(exc)}}))
        sys.exit(1)
    print(result if isinstance(result, str) else json.dumps({{"result": result}}))
'''


def _resolve_workspace_path(workspace_dir: Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` against ``workspace_dir``, refusing to
    escape it (e.g. via ``../..`` traversal or an absolute path elsewhere).

    Custom tool source must be a file the agent already wrote inside the
    workspace (with its normal filesystem tools) — never inline string
    content and never a path outside the workspace sandbox.
    """
    candidate = (workspace_dir / relative_path).resolve()
    workspace_resolved = workspace_dir.resolve()
    if candidate != workspace_resolved and workspace_resolved not in candidate.parents:
        raise ValueError(
            f"Path {relative_path!r} escapes the workspace directory "
            f"({workspace_resolved}); only files inside the workspace may be "
            "used as custom tool source."
        )
    return candidate


def _read_workspace_file(workspace_dir: Path, relative_path: str, *, label: str) -> str:
    path = _resolve_workspace_path(workspace_dir, relative_path)
    if not path.is_file():
        raise ValueError(
            f"{label} '{relative_path}' does not exist or is not a file "
            f"(resolved to {path}). Write the file first (e.g. with your "
            "filesystem tool), then pass its workspace-relative path here."
        )
    return path.read_text(encoding="utf-8")


def _require_workspace_files(workspace_dir: Path, required: dict[str, str | None]) -> None:
    """Verify that every required workspace-relative path in ``required``
    (a mapping of ``{label: path_or_None}``) points to an existing file
    *before* doing anything else. Raises a single ``ValueError`` listing
    every missing/unset entry at once, rather than failing one file at a
    time — the caller must write the file(s) first using its filesystem
    write tool, then pass the path(s) here.
    """
    problems = []
    for label, relative_path in required.items():
        if not relative_path:
            problems.append(f"{label} was not provided.")
            continue
        try:
            resolved = _resolve_workspace_path(workspace_dir, relative_path)
        except ValueError as e:
            problems.append(str(e))
            continue
        if not resolved.is_file():
            problems.append(
                f"{label} '{relative_path}' does not exist (resolved to {resolved}). "
                "Write it first with your filesystem write tool, then retry."
            )
    if problems:
        raise ValueError(
            "Required source file(s) are missing or invalid — write them with your "
            "filesystem tool before calling create_custom_tool:\n- " + "\n- ".join(problems)
        )


def create_custom_tool(
    workspace: str,
    name: str,
    description: str,
    kind: str,
    tool_args: dict[str, str] | None = None,
    python_source_path: str | None = None,
    dockerfile_path: str | None = None,
    entrypoint_path: str | None = None,
    network_access: bool = False,
    timeout_seconds: int = 30,
    created_by: str | None = None,
) -> CustomToolSpec:
    """Validate and write a new custom tool's files under
    ``<workspace>/custom_tools/<name>/``. Raises ``ValueError`` (never
    writes partial state) if validation fails.

    Source is always read from a file already written inside the
    workspace — never accepted as inline string content — identified by a
    workspace-relative path (``python_source_path`` for kind='python', or
    ``dockerfile_path``/``entrypoint_path`` for kind='docker'). Every
    required file is checked for existence up front (see
    `_require_workspace_files`), so a caller gets one combined error
    listing everything missing rather than failing one file at a time.
    """
    tool_args = tool_args or {}
    if not NAME_RE.match(name):
        raise ValueError(
            f"Invalid tool name {name!r}: must be snake_case, 3-64 chars, "
            "starting with a lowercase letter."
        )
    if kind not in ("python", "docker"):
        raise ValueError(f"Unknown kind {kind!r}; must be 'python' or 'docker'.")
    _validate_tool_args(tool_args)

    workspace_dir = Path(workspace)
    tool_dir = workspace_dir / "custom_tools" / name
    if tool_dir.exists():
        raise ValueError(
            f"A custom tool named '{name}' already exists at {tool_dir}. "
            "Remove it first (agentic tools custom remove) or pick a new name."
        )

    python_source = None
    dockerfile = None
    entrypoint_source = None

    if kind == "python":
        _require_workspace_files(workspace_dir, {"python_source_path": python_source_path})
        python_source = _read_workspace_file(
            workspace_dir, python_source_path, label="python_source_path"
        )
        violations = validate_python_source(python_source)
        if violations:
            raise ValueError(
                f"'{python_source_path}' failed validation:\n- " + "\n- ".join(violations)
            )
    else:
        _require_workspace_files(
            workspace_dir,
            {"dockerfile_path": dockerfile_path, "entrypoint_path": entrypoint_path},
        )
        dockerfile = _read_workspace_file(workspace_dir, dockerfile_path, label="dockerfile_path")
        entrypoint_source = _read_workspace_file(
            workspace_dir, entrypoint_path, label="entrypoint_path"
        )

    spec = CustomToolSpec(
        name=name,
        description=description,
        kind=kind,
        tool_args=tool_args,
        approved=False,
        approval_text=(
            f"Newly created custom tool '{name}' ({kind}): {description}. "
            "Review the args and generated source/Dockerfile before allowing."
        ),
        network_access=network_access,
        timeout_seconds=timeout_seconds,
        created_by=created_by,
    )

    # Only touch the filesystem once everything has validated successfully.
    tool_dir.mkdir(parents=True, exist_ok=False)
    try:
        if kind == "python":
            harness = _TOOL_HARNESS_TEMPLATE.format(user_source=python_source)
            (tool_dir / "tool.py").write_text(harness, encoding="utf-8")
        else:
            (tool_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")
            (tool_dir / "entrypoint").write_text(entrypoint_source, encoding="utf-8")
        (tool_dir / "spec.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(tool_dir, ignore_errors=True)
        raise

    logger.info(f"Custom tool '{name}' ({kind}) created at {tool_dir}")
    return spec


def _invalidate_docker_image(name: str) -> None:
    """Remove a cached docker image so the next call rebuilds it from the
    (possibly updated) Dockerfile. Best-effort: failures are logged, not
    raised, since a stale image is a performance concern, not a
    correctness one (the image will simply be rebuilt on demand, or the
    build will fail loudly on next use)."""
    tag = _docker_image_tag(name)
    try:
        subprocess.run(
            ["docker", "image", "rm", "-f", tag],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001
        logger.warning(f"Failed to invalidate cached docker image {tag}", exc_info=True)


def update_custom_tool(
    workspace: str,
    name: str,
    description: str | None = None,
    tool_args: dict[str, str] | None = None,
    python_source_path: str | None = None,
    dockerfile_path: str | None = None,
    entrypoint_path: str | None = None,
    network_access: bool | None = None,
    timeout_seconds: int | None = None,
    updated_by: str | None = None,
) -> CustomToolSpec:
    """Update an existing custom tool's metadata and/or source.

    Only the fields explicitly passed (non-``None``) are changed; everything
    else is left as-is. Like `create_custom_tool`, source is always read
    from a file already written inside the workspace (never inline string
    content), identified by a workspace-relative path.

    Every update — metadata-only or source — resets the tool's approval
    gate (``approved`` back to ``False``), since a human's earlier review
    no longer reflects the tool's current state; it must be re-reviewed
    via `agentic tools custom inspect` and re-promoted via
    `agentic tools custom approve` before it can run without per-call
    approval again.

    Raises ``ValueError`` (without touching any file) if the tool doesn't
    exist, the requested source file(s) are missing, or a source path is
    supplied for the wrong ``kind`` (e.g. ``python_source_path`` for a
    ``docker``-kind tool).
    """
    workspace_dir = Path(workspace)
    tool_dir = workspace_dir / "custom_tools" / name
    spec_path = tool_dir / "spec.json"
    if not spec_path.is_file():
        raise ValueError(
            f"No custom tool named '{name}' found at {tool_dir}. "
            "Use create_custom_tool to create it first."
        )
    spec = CustomToolSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))

    if tool_args is not None:
        _validate_tool_args(tool_args)

    if spec.kind == "python":
        if dockerfile_path or entrypoint_path:
            raise ValueError(
                f"Custom tool '{name}' is kind='python'; dockerfile_path/entrypoint_path "
                "are not applicable (did you mean python_source_path?)."
            )
    else:
        if python_source_path:
            raise ValueError(
                f"Custom tool '{name}' is kind='docker'; python_source_path is not "
                "applicable (did you mean dockerfile_path/entrypoint_path?)."
            )

    new_python_source = None
    new_dockerfile = None
    new_entrypoint_source = None

    if python_source_path is not None:
        _require_workspace_files(workspace_dir, {"python_source_path": python_source_path})
        new_python_source = _read_workspace_file(
            workspace_dir, python_source_path, label="python_source_path"
        )
        violations = validate_python_source(new_python_source)
        if violations:
            raise ValueError(
                f"'{python_source_path}' failed validation:\n- " + "\n- ".join(violations)
            )
    if dockerfile_path is not None:
        _require_workspace_files(workspace_dir, {"dockerfile_path": dockerfile_path})
        new_dockerfile = _read_workspace_file(workspace_dir, dockerfile_path, label="dockerfile_path")
    if entrypoint_path is not None:
        _require_workspace_files(workspace_dir, {"entrypoint_path": entrypoint_path})
        new_entrypoint_source = _read_workspace_file(
            workspace_dir, entrypoint_path, label="entrypoint_path"
        )

    if description is not None:
        spec.description = description
    if tool_args is not None:
        spec.tool_args = tool_args
    if network_access is not None:
        spec.network_access = network_access
    if timeout_seconds is not None:
        spec.timeout_seconds = timeout_seconds

    spec.approved = False
    spec.approval_text = (
        f"Custom tool '{name}' ({spec.kind}) was updated: {spec.description}. "
        "Review the (possibly changed) args/source/Dockerfile before allowing."
    )
    spec.updated_by = updated_by
    spec.updated_at = datetime.now(timezone.utc).isoformat()

    if new_python_source is not None:
        harness = _TOOL_HARNESS_TEMPLATE.format(user_source=new_python_source)
        (tool_dir / "tool.py").write_text(harness, encoding="utf-8")
    if new_dockerfile is not None:
        (tool_dir / "Dockerfile").write_text(new_dockerfile, encoding="utf-8")
    if new_entrypoint_source is not None:
        (tool_dir / "entrypoint").write_text(new_entrypoint_source, encoding="utf-8")
    (tool_dir / "spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")

    if spec.kind == "docker" and (new_dockerfile is not None or new_entrypoint_source is not None):
        _invalidate_docker_image(name)

    logger.info(f"Custom tool '{name}' ({spec.kind}) updated at {tool_dir}")
    return spec

def _run_python_tool(tool_dir: Path, timeout_seconds: int, **kwargs) -> str:
    # Must be absolute: we also pass `tool_dir` as the subprocess `cwd`
    # below, and a relative script path would be resolved a second time by
    # the child process against that (already-relocated) cwd, doubling the
    # directory segments in the final path.
    tool_dir = tool_dir.resolve()
    payload = json.dumps(kwargs)
    try:
        result = subprocess.run(
            ["uv", "run", "python", str(tool_dir / "tool.py")],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(tool_dir),
        )
    except subprocess.TimeoutExpired:
        return f"Error: custom tool timed out after {timeout_seconds}s"
    except Exception as e:  # noqa: BLE001 - surfaced to the caller
        return f"Error running custom tool: {e}"

    output = result.stdout.strip()
    if result.returncode != 0:
        stderr = result.stderr.strip()
        return f"Error running custom tool (exit {result.returncode}): {stderr or output}"
    return output or "(custom tool produced no output)"


def _docker_image_tag(name: str) -> str:
    return f"agentic-custom-tool-{name}:latest"


def _ensure_docker_image(spec: CustomToolSpec, tool_dir: Path) -> str | None:
    """Build the tool's docker image if it doesn't already exist. Returns an
    error string on failure, or None on success."""
    tag = _docker_image_tag(spec.name)
    try:
        inspect = subprocess.run(
            ["docker", "image", "inspect", tag],
            capture_output=True, text=True, timeout=10,
        )
        if inspect.returncode == 0:
            return None
        build = subprocess.run(
            ["docker", "build", "-t", tag, str(tool_dir)],
            capture_output=True, text=True, timeout=600,
        )
        if build.returncode != 0:
            return f"docker build failed: {build.stderr.strip() or build.stdout.strip()}"
    except FileNotFoundError:
        return "docker executable not found on PATH; cannot build/run docker-kind custom tools"
    except subprocess.TimeoutExpired:
        return "docker build timed out"
    except Exception as e:  # noqa: BLE001
        return f"docker build error: {e}"
    return None


def _run_docker_tool(spec: CustomToolSpec, tool_dir: Path, **kwargs) -> str:
    build_error = _ensure_docker_image(spec, tool_dir)
    if build_error:
        return f"Error: {build_error}"

    payload = json.dumps(kwargs)
    cmd = ["docker", "run", "--rm", "-i", "--memory", "256m", "--cpus", "1"]
    if not spec.network_access:
        cmd += ["--network", "none"]
    cmd.append(_docker_image_tag(spec.name))

    try:
        result = subprocess.run(
            cmd, input=payload, capture_output=True, text=True,
            timeout=spec.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return f"Error: custom tool timed out after {spec.timeout_seconds}s"
    except Exception as e:  # noqa: BLE001
        return f"Error running docker custom tool: {e}"

    output = result.stdout.strip()
    if result.returncode != 0:
        stderr = result.stderr.strip()
        return f"Error running docker custom tool (exit {result.returncode}): {stderr or output}"
    return output or "(custom tool produced no output)"


class CustomToolLoader:
    """Discovers and loads custom tools from ``<workspace>/custom_tools/``."""

    def __init__(self, workspace: str):
        # Resolve to an absolute path up front. `workspace` is commonly a
        # relative path (e.g. "./workspace" from an agent's config). If left
        # relative, `_run_python_tool` below passes a relative script path
        # *and* sets that same relative directory as the subprocess `cwd`,
        # causing the child process to resolve the script path a second time
        # against its own (already-relocated) cwd — doubling the
        # `custom_tools/<name>` segment in the final path.
        self.base_dir = Path(workspace).resolve() / "custom_tools"

    def list_specs(self) -> list[CustomToolSpec]:
        if not self.base_dir.is_dir():
            return []
        specs = []
        for entry in sorted(self.base_dir.iterdir()):
            spec_path = entry / "spec.json"
            if entry.is_dir() and spec_path.is_file():
                try:
                    specs.append(
                        CustomToolSpec.model_validate_json(
                            spec_path.read_text(encoding="utf-8")
                        )
                    )
                except Exception:
                    logger.warning(f"Failed to parse custom tool spec at {spec_path}", exc_info=True)
        return specs

    def load_all(self) -> list[BaseTool]:
        tools = []
        for spec in self.list_specs():
            tool_dir = self.base_dir / spec.name
            try:
                tools.append(self._build_tool(spec, tool_dir))
            except Exception:
                logger.exception(f"Failed to load custom tool '{spec.name}'")
        return tools

    def _build_tool(self, spec: CustomToolSpec, tool_dir: Path) -> StructuredTool:
        args_model = _build_args_model(spec.name, spec.tool_args)

        if spec.kind == "python":
            def _run(**kwargs):
                return _run_python_tool(tool_dir, spec.timeout_seconds, **kwargs)
        else:
            def _run(**kwargs):
                return _run_docker_tool(spec, tool_dir, **kwargs)

        return StructuredTool.from_function(
            func=_run,
            name=spec.name,
            description=spec.description,
            args_schema=args_model,
        )

    def update(self, name: str, **kwargs) -> CustomToolSpec:
        """Thin wrapper around the module-level `update_custom_tool`, for
        symmetry with `approve`/`remove` on this loader. See that
        function's docstring for the full contract."""
        return update_custom_tool(workspace=str(self.base_dir.parent), name=name, **kwargs)

    def approve(self, name: str) -> CustomToolSpec:
        tool_dir = self.base_dir / name
        spec_path = tool_dir / "spec.json"
        if not spec_path.is_file():
            raise FileNotFoundError(f"No custom tool named '{name}' found at {tool_dir}")
        spec = CustomToolSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
        spec.approved = True
        spec_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        return spec

    def remove(self, name: str) -> None:
        tool_dir = self.base_dir / name
        if not tool_dir.is_dir():
            raise FileNotFoundError(f"No custom tool named '{name}' found at {tool_dir}")
        shutil.rmtree(tool_dir)

