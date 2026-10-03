# Proxmox Environment Template and CRUD CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reusable multi-cluster Proxmox VE environment template and a safe CLI for VM and LXC REST API CRUD.

**Architecture:** A Python CLI reads a YAML manifest, selects an independent cluster, and sends Proxmox API-token-authenticated requests. Documentation and a non-secret example manifest remain separate from executable code.

**Tech Stack:** Python 3.14+, PyYAML, `urllib.request`, pytest, `unittest.mock`, Markdown.

## Global Constraints

- Support virtual machines and LXC containers only.
- Support one or more independent manifest clusters.
- Read credentials only from `PROXMOX_API_TOKEN_ID` and `PROXMOX_API_TOKEN_SECRET`.
- Use `https://<cluster-url>:8006/api2/json`; do not store secrets in files.
- Verify TLS by default; allow an explicit `--insecure` development opt-out.
- Require `--confirm` for deletion and permit `--dry-run` for mutations.
- Print malformed document and API errors to stderr, returning non-zero status.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Declare PyYAML. |
| `scripts/proxmox_crud.py` | Validate manifests, make REST requests, and implement CLI CRUD. |
| `tests/unit/test_proxmox_crud.py` | Test transport, selection, mutations, safeguards, and docs. |
| `docs/proxmox-manifest.example.yaml` | Copyable two-cluster VM/LXC input. |
| `docs/proxmox-environment-template.md` | Fill-in runbook and REST/CLI guide. |

### Task 1: Add the validated manifest and API client

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/proxmox_crud.py`
- Test: `tests/unit/test_proxmox_crud.py`

**Interfaces:**
- Produces `load_manifest(path: Path) -> dict`,
  `select_cluster(manifest: dict, name: str) -> dict`,
  `resource_endpoint(resource_type: str, node: str, vmid: int) -> str`, and
  `ProxmoxClient.request(method: str, path: str, data: dict | None = None) -> dict`.

- [ ] **Step 1: Write failing primitive tests**

```python
def test_select_cluster_and_build_vm_endpoint():
    manifest = {
        "clusters": [{"name": "lab", "api_url": "pve.lab.example", "resources": []}]
    }
    assert proxmox.select_cluster(manifest, "lab")["api_url"] == "pve.lab.example"
    assert proxmox.resource_endpoint("vm", "pve-01", 101) == "/nodes/pve-01/qemu/101"


def test_client_uses_api_token_header(mocker):
    opened = mocker.patch("proxmox_crud.urlopen")
    opened.return_value.__enter__.return_value.read.return_value = b'{"data": {}}'
    proxmox.ProxmoxClient("pve.lab.example", "root@pam!automation", "secret").request(
        "GET", "/version"
    )
    assert (
        opened.call_args.args[0].get_header("Authorization")
        == "PVEAPIToken=root@pam!automation=secret"
    )
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/unit/test_proxmox_crud.py -q`

Expected: FAIL because the client module does not exist.

- [ ] **Step 3: Implement the primitives**

Add `"pyyaml>=6.0.3"` to `pyproject.toml`. Use `yaml.safe_load` and reject a
non-mapping root, duplicate/missing cluster names, missing API URLs or
resources, and resources with invalid `type` (`vm`/`lxc`), `node`, or integer
`vmid`.

```python
def resource_endpoint(resource_type: str, node: str, vmid: int) -> str:
    segment = {"vm": "qemu", "lxc": "lxc"}.get(resource_type)
    if segment is None:
        raise ValueError("resource event_type must be 'vm' or 'lxc'")
    return f"/nodes/{quote(node, safe='')}/{segment}/{vmid}"
```

Build requests with `urllib.request.Request`, URL-encoded mutation payloads,
JSON decoding, and `PVEAPIToken=<id>=<secret>`. Use a verified SSL context
unless `--insecure` is set. Convert HTTP/URL errors to `RuntimeError`
containing method, path, status when available, and body.

- [ ] **Step 4: Lock dependencies and run the focused test**

Run: `uv lock && uv run pytest tests/unit/test_proxmox_crud.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock scripts/proxmox_crud.py tests/unit/test_proxmox_crud.py
git commit -m "feat: add Proxmox API client core"
```

### Task 2: Add safe VM and LXC CRUD commands

**Files:**
- Modify: `scripts/proxmox_crud.py`
- Modify: `tests/unit/test_proxmox_crud.py`

**Interfaces:**
- Consumes the Task 1 client and resources with `type`, `node`, `vmid`, and
  API fields.
- Produces `main(argv: list[str] | None = None) -> int` with `create`, `read`,
  `update`, and `delete` subcommands.

- [ ] **Step 1: Write failing command tests**

```python
def test_create_posts_vm_resource_to_collection(mocker, manifest_file):
    request = mocker.patch.object(
        proxmox.ProxmoxClient, "request", return_value={"data": "UPID:node:task"}
    )
    assert (
        proxmox.main(["create", "--file", str(manifest_file), "--cluster", "lab"]) == 0
    )
    assert request.call_args.args == (
        "POST",
        "/nodes/pve-01/qemu",
        {"vmid": 101, "name": "web-01", "cores": 2, "memory": 2048},
    )


def test_delete_requires_confirm(mocker):
    request = mocker.patch.object(proxmox.ProxmoxClient, "request")
    assert (
        proxmox.main(
            [
                "delete",
                "--file",
                "manifest.yaml",
                "--cluster",
                "lab",
                "--node",
                "pve-01",
                "--event_type",
                "lxc",
                "--vmid",
                "200",
            ]
        )
        == 2
    )
    request.assert_not_called()
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/unit/test_proxmox_crud.py -q`

Expected: FAIL because the subcommands do not exist.

- [ ] **Step 3: Implement command parsing and REST calls**

Use `argparse` subcommands. `create` and `update` accept `--file`,
`--cluster`, an optional resource selector, and `--dry-run`. `read` and
`delete` accept `--file`, `--cluster`, `--node`, `--type`, and `--vmid`;
`delete` also requires `--confirm`.

```text
create: POST /nodes/{node}/qemu|lxc
read:   GET  /nodes/{node}/qemu|lxc/{vmid}/config
update: PUT  /nodes/{node}/qemu|lxc/{vmid}/config
delete: DELETE /nodes/{node}/qemu|lxc/{vmid}
```

Create payloads omit `type` and `node`; update payloads also omit `vmid`,
`ostemplate`, and manifest metadata. A dry run prints method, path, and a
redacted JSON payload without instantiating an HTTP client. Return `0` on
success, `1` on API failures, and `2` for invalid input or missing
confirmation.

- [ ] **Step 4: Run the focused test**

Run: `uv run pytest tests/unit/test_proxmox_crud.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/proxmox_crud.py tests/unit/test_proxmox_crud.py
git commit -m "feat: add safe Proxmox CRUD commands"
```

### Task 3: Add the reusable documentation

**Files:**
- Create: `docs/proxmox-manifest.example.yaml`
- Create: `docs/proxmox-environment-template.md`
- Modify: `tests/unit/test_proxmox_crud.py`

**Interfaces:**
- Consumes the Task 1 manifest schema and Task 2 CLI flags.
- Produces copyable operational and command documentation.

- [ ] **Step 1: Write failing documentation tests**

```python
def test_example_manifest_is_accepted():
    manifest = proxmox.load_manifest(Path("docs/proxmox-manifest.example.yaml"))
    assert {item["name"] for item in manifest["clusters"]} == {
        "primary-cluster",
        "secondary-cluster",
    }


def test_template_documents_all_commands():
    text = Path("docs/proxmox-environment-template.md").read_text(encoding="utf-8")
    assert all(
        f"`{command}`" in text for command in ("create", "read", "update", "delete")
    )
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/unit/test_proxmox_crud.py -q`

Expected: FAIL because both documents do not exist.

- [ ] **Step 3: Write the manifest and runbook**

Create two clusters named `primary-cluster` and `secondary-cluster`, each with
a placeholder API URL. Include a non-secret VM and LXC with `vmid`, `name`,
`node`, `cores`, and `memory`; give only the LXC resource `ostemplate`.

Create a template with `[PLACEHOLDER]` fields and repeatable tables for
clusters, nodes, storage, networks, owners, support, token references, and
backup, monitoring, and runbook links. Document token environment variables,
all four CLI commands, dry-run/deletion examples, API base path/header/common
endpoints, UPID polling, errors, TLS, and least-privilege ACLs.

- [ ] **Step 4: Run full validation**

Run: `uv run pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/proxmox-manifest.example.yaml docs/proxmox-environment-template.md tests/unit/test_proxmox_crud.py
git commit -m "docs: add Proxmox environment template"
```
