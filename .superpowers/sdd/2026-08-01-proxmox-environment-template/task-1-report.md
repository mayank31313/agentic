# Task 1 Report

## Status

DONE

## Files changed

- `pyproject.toml` — added `pyyaml>=6.0.3`
- `uv.lock` — resolved and locked the new dependency
- `scripts/proxmox_crud.py` — manifest validation, endpoint building, and Proxmox API client
- `proxmox_crud.py` — top-level alias to the same client module
- `tests/unit/test_proxmox_crud.py` — focused Task 1 tests

## Commit

- `e01ba06` — `feat: add Proxmox API client core`

## Tests run

- `uv run pytest tests/unit/test_proxmox_crud.py -q`
  - initial expected failure: `1 error during collection` / `ModuleNotFoundError: No module named 'scripts.proxmox_crud'`
- `uv lock`
  - `Resolved 143 packages in 4ms`
- `uv run pytest tests/unit/test_proxmox_crud.py -q`
  - `7 passed in 0.33s`

## Design choices

- Validated YAML with `yaml.safe_load` and rejected non-mapping roots.
- Enforced cluster-name uniqueness, required `api_url`, and required `resources` lists.
- Validated resources for `type` (`vm`/`lxc`), `node`, and integer `vmid`.
- Normalized cluster API URLs to Proxmox’s `https://<host>:8006/api2/json` base path.
- Built requests with `urllib.request.Request`, API-token auth, form-encoded payloads, and JSON decoding.
- Used verified TLS by default and an explicit `insecure` opt-out on the client.
- Converted HTTP/URL failures into `RuntimeError` with method, path, status, and body details.
- Added a top-level shim so both `proxmox_crud` and `scripts.proxmox_crud` resolve to the same module.

## Concerns

- The worktree already contained many unrelated dirty changes; none were modified.
- Task 1 does not implement CRUD subcommands or documentation yet; those remain for later tasks.

## Fix round 1

### Status

DONE

### Files changed

- `scripts/proxmox_crud.py` — hardened API URL validation and rejected empty cluster lists
- `tests/unit/test_proxmox_crud.py` — added regression tests for API URL constraints and empty clusters
- `task-1-report.md` — appended this fix-round report

### Commit

- `PENDING` — fix-round commit created after this update

### Test command / output summary

- `uv run pytest tests/unit/test_proxmox_crud.py -q`
  - `14 passed in 0.30s`

### Resolution details

- `_normalize_api_url()` now rejects non-HTTPS schemes, userinfo, query/fragment parts, paths, and ports other than `8006`, and always normalizes accepted input to `https://<host>:8006/api2/json`.
- `load_manifest()` now rejects `clusters: []` with a clear error that at least one cluster is required.
