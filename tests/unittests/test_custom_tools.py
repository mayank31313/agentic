"""Unit tests for agentic.app.common.custom_tools (agent-authored tools)."""

import json
import os

import pytest

from agentic.app.common.custom_tools import (
    CustomToolLoader,
    CustomToolSpec,
    create_custom_tool,
    update_custom_tool,
    validate_python_source,
)


# --------------------------------------------------------------------------
# validate_python_source
# --------------------------------------------------------------------------

def test_validate_python_source_accepts_clean_source():
    source = "def run(**kwargs):\n    return kwargs.get('x', 0) + 1\n"
    assert validate_python_source(source) == []


def test_validate_python_source_requires_top_level_run_function():
    violations = validate_python_source("def other():\n    return 1\n")
    assert any("run(**kwargs)" in v for v in violations)


def test_validate_python_source_rejects_disallowed_import():
    violations = validate_python_source(
        "import os\n\ndef run(**kwargs):\n    return os.getcwd()\n"
    )
    assert any("Import of 'os'" in v for v in violations)


def test_validate_python_source_rejects_forbidden_call():
    violations = validate_python_source(
        "def run(**kwargs):\n    return eval(kwargs['expr'])\n"
    )
    assert any("eval(...)" in v for v in violations)


def test_validate_python_source_rejects_forbidden_attribute_access():
    violations = validate_python_source(
        "def run(**kwargs):\n    return os.system('ls')\n"
    )
    assert any("os.system" in v for v in violations)


def test_validate_python_source_rejects_syntax_error():
    violations = validate_python_source("def run(**kwargs:\n    pass")
    assert any("SyntaxError" in v for v in violations)


def test_validate_python_source_allows_allow_listed_imports():
    source = "import json\nimport math\n\ndef run(**kwargs):\n    return math.sqrt(4)\n"
    assert validate_python_source(source) == []


# --------------------------------------------------------------------------
# create_custom_tool (file-path based source)
# --------------------------------------------------------------------------

def _write(tmp_path, relative_path, content):
    """Write ``content`` to ``tmp_path/relative_path`` (creating parent
    dirs), returning the workspace-relative path string to pass to
    ``create_custom_tool`` — mirrors an agent using its filesystem write
    tool before calling create_custom_tool.
    """
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return relative_path


def test_create_custom_tool_writes_python_tool_files(tmp_path):
    src_path = _write(tmp_path, "src/add_one.py", "def run(**kwargs):\n    return kwargs['x'] + 1\n")

    spec = create_custom_tool(
        workspace=str(tmp_path),
        name="add_one",
        description="Adds one to a number",
        kind="python",
        tool_args={"x": "integer"},
        python_source_path=src_path,
    )

    assert isinstance(spec, CustomToolSpec)
    assert spec.approved is False
    tool_dir = tmp_path / "custom_tools" / "add_one"
    assert (tool_dir / "tool.py").is_file()
    assert (tool_dir / "spec.json").is_file()
    saved = json.loads((tool_dir / "spec.json").read_text(encoding="utf-8"))
    assert saved["name"] == "add_one"
    assert saved["kind"] == "python"


def test_create_custom_tool_requires_python_source_path(tmp_path):
    with pytest.raises(ValueError, match="was not provided"):
        create_custom_tool(
            workspace=str(tmp_path),
            name="no_path_tool",
            description="x",
            kind="python",
        )


def test_create_custom_tool_rejects_unknown_tool_arg_type(tmp_path):
    """Regression test: an unrecognized tool_args type name (e.g. a typo)
    must raise loudly and write nothing, rather than silently defaulting the
    argument to `str` (see `_validate_tool_args`).
    """
    src_path = _write(tmp_path, "src/bad_type.py", "def run(**kwargs):\n    return 1\n")
    with pytest.raises(ValueError, match="Unknown tool_args type"):
        create_custom_tool(
            workspace=str(tmp_path),
            name="bad_type_tool",
            description="x",
            kind="python",
            tool_args={"n": "not_a_real_type"},
            python_source_path=src_path,
        )
    assert not (tmp_path / "custom_tools" / "bad_type_tool").exists()


def test_custom_tool_int_alias_coerces_arg_to_int_not_str(tmp_path):
    """Regression test for the bug where a `tool_args` type of "int"
    (rather than the canonical "integer") silently fell back to `str` in
    `_build_args_model`, causing numeric arguments to be sent to the tool's
    subprocess as JSON strings and blow up with e.g.
    `TypeError: '<' not supported between instances of 'str' and 'int'`.
    """
    src_path = _write(
        tmp_path,
        "src/needs_int.py",
        "def run(target_number=0):\n    return target_number < 5\n",
    )
    create_custom_tool(
        workspace=str(tmp_path),
        name="needs_int_tool",
        description="x",
        kind="python",
        tool_args={"target_number": "int"},
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    tool = loader.load_all()[0]
    # If "int" were still mistakenly coerced to str, invoking with a JSON
    # integer would fail pydantic validation or the subprocess would
    # receive a string and raise the TypeError described above.
    result = tool.invoke({"target_number": 3})
    assert json.loads(result) == {"result": True}



def test_create_custom_tool_rejects_missing_source_file(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        create_custom_tool(
            workspace=str(tmp_path),
            name="missing_file_tool",
            description="x",
            kind="python",
            python_source_path="src/does_not_exist.py",
        )


def test_create_custom_tool_rejects_path_escaping_workspace(tmp_path):
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / "evil.py").write_text("def run(**kwargs):\n    return 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes the workspace"):
        create_custom_tool(
            workspace=str(tmp_path),
            name="escape_tool",
            description="x",
            kind="python",
            python_source_path="../outside/evil.py",
        )


def test_create_custom_tool_rejects_invalid_name(tmp_path):
    src_path = _write(tmp_path, "src/x.py", "def run(**kwargs):\n    return 1\n")
    with pytest.raises(ValueError, match="Invalid tool name"):
        create_custom_tool(
            workspace=str(tmp_path),
            name="BadName!",
            description="x",
            kind="python",
            python_source_path=src_path,
        )


def test_create_custom_tool_rejects_bad_python_source_without_writing_files(tmp_path):
    src_path = _write(
        tmp_path, "src/bad.py", "import os\n\ndef run(**kwargs):\n    return os.getcwd()\n"
    )
    with pytest.raises(ValueError, match="failed validation"):
        create_custom_tool(
            workspace=str(tmp_path),
            name="bad_tool",
            description="x",
            kind="python",
            python_source_path=src_path,
        )
    assert not (tmp_path / "custom_tools" / "bad_tool").exists()


def test_create_custom_tool_rejects_duplicate_name(tmp_path):
    src_path = _write(tmp_path, "src/dup.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path),
        name="dup_tool",
        description="x",
        kind="python",
        python_source_path=src_path,
    )
    with pytest.raises(ValueError, match="already exists"):
        create_custom_tool(
            workspace=str(tmp_path),
            name="dup_tool",
            description="y",
            kind="python",
            python_source_path=src_path,
        )


def test_create_custom_tool_requires_dockerfile_and_entrypoint_for_docker_kind(tmp_path):
    with pytest.raises(ValueError, match="dockerfile_path was not provided") as exc_info:
        create_custom_tool(
            workspace=str(tmp_path),
            name="docker_tool",
            description="x",
            kind="docker",
        )
    # Both missing files should be reported together, not one at a time.
    assert "entrypoint_path was not provided" in str(exc_info.value)


def test_create_custom_tool_reports_all_missing_files_at_once(tmp_path):
    dockerfile_path = _write(tmp_path, "src/Dockerfile", "FROM python:3.14-slim\n")
    # entrypoint_path deliberately points to a file that was never written.
    with pytest.raises(ValueError) as exc_info:
        create_custom_tool(
            workspace=str(tmp_path),
            name="partial_docker_tool",
            description="x",
            kind="docker",
            dockerfile_path=dockerfile_path,
            entrypoint_path="src/missing_entrypoint",
        )
    assert "missing_entrypoint" in str(exc_info.value)
    assert "does not exist" in str(exc_info.value)


def test_create_custom_tool_writes_docker_tool_files(tmp_path):
    dockerfile_path = _write(
        tmp_path, "src/Dockerfile",
        "FROM python:3.14-slim\nCOPY entrypoint /entrypoint\nENTRYPOINT [\"python\", \"/entrypoint\"]\n",
    )
    entrypoint_path = _write(tmp_path, "src/entrypoint", "print('hello')\n")

    spec = create_custom_tool(
        workspace=str(tmp_path),
        name="docker_tool",
        description="x",
        kind="docker",
        dockerfile_path=dockerfile_path,
        entrypoint_path=entrypoint_path,
    )
    tool_dir = tmp_path / "custom_tools" / "docker_tool"
    assert spec.kind == "docker"
    assert (tool_dir / "Dockerfile").is_file()
    assert (tool_dir / "entrypoint").is_file()


# --------------------------------------------------------------------------
# CustomToolLoader
# --------------------------------------------------------------------------

def test_loader_list_specs_empty_when_no_custom_tools_dir(tmp_path):
    loader = CustomToolLoader(str(tmp_path))
    assert loader.list_specs() == []


def test_loader_list_specs_returns_created_tools(tmp_path):
    src_path = _write(tmp_path, "src/a.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path),
        name="tool_a",
        description="A",
        kind="python",
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    specs = loader.list_specs()
    assert [s.name for s in specs] == ["tool_a"]


def test_loader_approve_sets_flag_and_persists(tmp_path):
    src_path = _write(tmp_path, "src/b.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path),
        name="tool_b",
        description="B",
        kind="python",
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    spec = loader.approve("tool_b")
    assert spec.approved is True

    # Re-load from disk to confirm persistence.
    reloaded = loader.list_specs()[0]
    assert reloaded.approved is True


def test_loader_approve_raises_for_unknown_tool(tmp_path):
    loader = CustomToolLoader(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        loader.approve("does_not_exist")


def test_loader_base_dir_is_absolute_even_for_relative_workspace(tmp_path, monkeypatch):
    """Regression test: a relative `workspace` (e.g. "./workspace", the
    default `workspace_dir` in agent configs) must not leave `base_dir`
    relative. Previously, a relative `tool_dir` was used both as the
    subprocess `cwd` *and* to build the script path argument in
    `_run_python_tool`, causing the child process to resolve the relative
    script path a second time against its already-relocated cwd — doubling
    the `custom_tools/<name>` segment (e.g.
    `.../custom_tools/foo/custom_tools/foo/tool.py`).
    """
    monkeypatch.chdir(tmp_path)
    loader = CustomToolLoader("./workspace")
    assert loader.base_dir.is_absolute()
    assert loader.base_dir == (tmp_path / "workspace" / "custom_tools").resolve()


def test_run_python_tool_works_with_relative_workspace(tmp_path, monkeypatch):
    """End-to-end regression test for the path-doubling bug: create and run
    a custom tool using a relative `workspace` path while the process cwd is
    unrelated to the workspace root, and confirm it actually executes.
    """
    workspace_dir = tmp_path / "workspace"
    src_path = _write(workspace_dir, "src/fib.py", "def run(**kwargs):\n    return 42\n")
    create_custom_tool(
        workspace=str(workspace_dir),
        name="fibonacci_calculator",
        description="Computes fibonacci numbers",
        kind="python",
        python_source_path=src_path,
    )

    # Simulate the real runtime: the app's cwd is the project root, and
    # `workspace_dir` is a relative path like "./workspace" underneath it.
    monkeypatch.chdir(tmp_path)
    loader = CustomToolLoader("./workspace")
    tool = loader.load_all()[0]
    result = tool.invoke({})
    assert result == json.dumps({"result": 42})


def test_loader_remove_deletes_directory(tmp_path):
    src_path = _write(tmp_path, "src/c.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path),
        name="tool_c",
        description="C",
        kind="python",
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    loader.remove("tool_c")
    assert not (tmp_path / "custom_tools" / "tool_c").exists()
    assert loader.list_specs() == []


def test_loader_load_all_builds_structured_tools(tmp_path):
    src_path = _write(tmp_path, "src/d.py", "def run(**kwargs):\n    return kwargs['x'] + 1\n")
    create_custom_tool(
        workspace=str(tmp_path),
        name="tool_d",
        description="D does something",
        kind="python",
        tool_args={"x": "integer"},
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    tools = loader.load_all()
    assert len(tools) == 1
    assert tools[0].name == "tool_d"
    assert tools[0].description == "D does something"


def test_run_python_tool_executes_and_returns_output(tmp_path):
    """End-to-end: create a real python custom tool and invoke it via a
    subprocess (uv run python). Requires `uv` to be on PATH like the rest
    of the project's tooling; skipped if unavailable.
    """
    import shutil

    if shutil.which("uv") is None:
        pytest.skip("uv executable not available in this environment")

    src_path = _write(tmp_path, "src/adder.py", "def run(**kwargs):\n    return kwargs['x'] + 1\n")
    create_custom_tool(
        workspace=str(tmp_path),
        name="adder",
        description="adds one",
        kind="python",
        tool_args={"x": "integer"},
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    tools = loader.load_all()
    result = tools[0].invoke({"x": 41})
    assert "42" in str(result)


# --------------------------------------------------------------------------
# update_custom_tool
# --------------------------------------------------------------------------

def test_update_custom_tool_raises_for_unknown_tool(tmp_path):
    with pytest.raises(ValueError, match="No custom tool named"):
        update_custom_tool(workspace=str(tmp_path), name="does_not_exist", description="x")


def test_update_custom_tool_changes_description_and_resets_approval(tmp_path):
    src_path = _write(tmp_path, "src/e.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_e", description="old desc", kind="python",
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    loader.approve("tool_e")
    assert loader.list_specs()[0].approved is True

    spec = update_custom_tool(workspace=str(tmp_path), name="tool_e", description="new desc")
    assert spec.description == "new desc"
    assert spec.approved is False  # any edit resets the approval gate
    assert spec.updated_at is not None

    reloaded = loader.list_specs()[0]
    assert reloaded.description == "new desc"
    assert reloaded.approved is False


def test_update_custom_tool_replaces_python_source(tmp_path):
    src_path = _write(tmp_path, "src/f.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_f", description="d", kind="python",
        python_source_path=src_path,
    )
    new_src_path = _write(tmp_path, "src/f_v2.py", "def run(**kwargs):\n    return 2\n")
    update_custom_tool(workspace=str(tmp_path), name="tool_f", python_source_path=new_src_path)

    tool_py = (tmp_path / "custom_tools" / "tool_f" / "tool.py").read_text(encoding="utf-8")
    assert "return 2" in tool_py


def test_update_custom_tool_rejects_bad_new_python_source(tmp_path):
    src_path = _write(tmp_path, "src/g.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_g", description="d", kind="python",
        python_source_path=src_path,
    )
    bad_src_path = _write(
        tmp_path, "src/g_bad.py", "import os\n\ndef run(**kwargs):\n    return os.getcwd()\n"
    )
    with pytest.raises(ValueError, match="failed validation"):
        update_custom_tool(workspace=str(tmp_path), name="tool_g", python_source_path=bad_src_path)

    # Original source must be untouched since validation failed.
    tool_py = (tmp_path / "custom_tools" / "tool_g" / "tool.py").read_text(encoding="utf-8")
    assert "return 1" in tool_py


def test_update_custom_tool_rejects_python_source_path_on_docker_tool(tmp_path):
    dockerfile_path = _write(tmp_path, "src/Dockerfile", "FROM python:3.14-slim\n")
    entrypoint_path = _write(tmp_path, "src/entrypoint", "print('hi')\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_h", description="d", kind="docker",
        dockerfile_path=dockerfile_path, entrypoint_path=entrypoint_path,
    )
    with pytest.raises(ValueError, match="is kind='docker'"):
        update_custom_tool(workspace=str(tmp_path), name="tool_h", python_source_path="src/whatever.py")


def test_update_custom_tool_replaces_dockerfile_and_entrypoint(tmp_path):
    dockerfile_path = _write(tmp_path, "src/Dockerfile", "FROM python:3.14-slim\n")
    entrypoint_path = _write(tmp_path, "src/entrypoint", "print('hi')\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_i", description="d", kind="docker",
        dockerfile_path=dockerfile_path, entrypoint_path=entrypoint_path,
    )
    new_dockerfile_path = _write(tmp_path, "src/Dockerfile_v2", "FROM python:3.14-slim\nRUN echo hi\n")
    update_custom_tool(workspace=str(tmp_path), name="tool_i", dockerfile_path=new_dockerfile_path)

    dockerfile = (tmp_path / "custom_tools" / "tool_i" / "Dockerfile").read_text(encoding="utf-8")
    assert "RUN echo hi" in dockerfile


def test_update_custom_tool_rejects_missing_new_source_file(tmp_path):
    src_path = _write(tmp_path, "src/j.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_j", description="d", kind="python",
        python_source_path=src_path,
    )
    with pytest.raises(ValueError, match="does not exist"):
        update_custom_tool(workspace=str(tmp_path), name="tool_j", python_source_path="src/nope.py")


def test_update_custom_tool_updates_tool_args_and_metadata_only(tmp_path):
    src_path = _write(tmp_path, "src/k.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_k", description="d", kind="python",
        python_source_path=src_path, timeout_seconds=10,
    )
    spec = update_custom_tool(
        workspace=str(tmp_path), name="tool_k",
        tool_args={"x": "integer"}, timeout_seconds=60,
    )
    assert spec.tool_args == {"x": "integer"}
    assert spec.timeout_seconds == 60
    assert spec.description == "d"  # unchanged since not passed


def test_update_custom_tool_rejects_unknown_tool_arg_type(tmp_path):
    src_path = _write(tmp_path, "src/m.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_m", description="d", kind="python",
        python_source_path=src_path,
    )
    with pytest.raises(ValueError, match="Unknown tool_args type"):
        update_custom_tool(
            workspace=str(tmp_path), name="tool_m",
            tool_args={"x": "not_a_real_type"},
        )
    # Metadata must be unchanged since the update was rejected.
    spec = CustomToolLoader(str(tmp_path)).list_specs()[0]
    assert spec.tool_args == {}


def test_loader_update_wraps_module_function(tmp_path):
    src_path = _write(tmp_path, "src/l.py", "def run(**kwargs):\n    return 1\n")
    create_custom_tool(
        workspace=str(tmp_path), name="tool_l", description="old", kind="python",
        python_source_path=src_path,
    )
    loader = CustomToolLoader(str(tmp_path))
    spec = loader.update("tool_l", description="new")
    assert spec.description == "new"
