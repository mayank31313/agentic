from pathlib import Path
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from urllib.error import HTTPError

import scripts.proxmox_crud as proxmox


def test_select_cluster_and_build_vm_endpoint():
    manifest = {
        "clusters": [
            {"name": "lab", "api_url": "pve.lab.example", "resources": []}
        ]
    }
    assert proxmox.select_cluster(manifest, "lab")["api_url"] == "pve.lab.example"
    assert proxmox.resource_endpoint("vm", "pve-01", 101) == "/nodes/pve-01/qemu/101"


def test_client_uses_api_token_header(monkeypatch):
    opened = MagicMock()
    response = MagicMock()
    response.read.return_value = b'{"data": {}}'
    opened.return_value.__enter__.return_value = response
    monkeypatch.setattr(proxmox, "urlopen", opened)

    proxmox.ProxmoxClient("pve.lab.example", "root@pam!automation", "secret").request(
        "GET",
        "/version",
    )

    assert (
        opened.call_args.args[0].get_header("Authorization")
        == "PVEAPIToken=root@pam!automation=secret"
    )


def test_load_manifest_and_validate_clusters(tmp_path: Path):
    manifest_path = tmp_path / "manifest.yml"
    manifest_path.write_text(
        "clusters:\n"
        "  - name: lab\n"
        "    api_url: pve.lab.example\n"
        "    resources:\n"
        "      - type: vm\n"
        "        node: pve-01\n"
        "        vmid: 101\n",
        encoding="utf-8",
    )

    manifest = proxmox.load_manifest(manifest_path)

    assert manifest["clusters"][0]["name"] == "lab"


def test_load_manifest_rejects_non_mapping(tmp_path: Path):
    manifest_path = tmp_path / "manifest.yml"
    manifest_path.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="root must be a mapping"):
        proxmox.load_manifest(manifest_path)


def test_load_manifest_rejects_duplicate_cluster_names(tmp_path: Path):
    manifest_path = tmp_path / "manifest.yml"
    manifest_path.write_text(
        "clusters:\n"
        "  - name: lab\n"
        "    api_url: pve-01\n"
        "    resources: []\n"
        "  - name: lab\n"
        "    api_url: pve-02\n"
        "    resources: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate cluster name 'lab'"):
        proxmox.load_manifest(manifest_path)


def test_load_manifest_rejects_invalid_resource_type(tmp_path: Path):
    manifest_path = tmp_path / "manifest.yml"
    manifest_path.write_text(
        "clusters:\n"
        "  - name: lab\n"
        "    api_url: pve.lab.example\n"
        "    resources:\n"
        "      - type: disk\n"
        "        node: pve-01\n"
        "        vmid: 101\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="type must be 'vm' or 'lxc'"):
        proxmox.load_manifest(manifest_path)


def test_client_wraps_http_error(monkeypatch):
    error = HTTPError(
        "https://pve.lab.example:8006/api2/json/version",
        500,
        "Internal Server Error",
        hdrs=None,
        fp=BytesIO(b'{"error":"boom"}'),
    )
    monkeypatch.setattr(proxmox, "urlopen", MagicMock(side_effect=error))

    client = proxmox.ProxmoxClient("pve.lab.example", "root@pam!automation", "secret")

    with pytest.raises(RuntimeError, match=r"GET /version failed with HTTP 500: .*boom"):
        client.request("GET", "/version")
