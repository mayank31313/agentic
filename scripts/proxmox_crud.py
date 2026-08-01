from __future__ import annotations

import json
import ssl
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import yaml


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _manifest_error(message: str) -> ValueError:
    return ValueError(message)


def _validate_resource(resource: Any, cluster_name: str, index: int) -> dict[str, Any]:
    if not isinstance(resource, dict):
        raise _manifest_error(f"cluster '{cluster_name}' resource {index} must be a mapping")

    resource_type = resource.get("type")
    if resource_type not in {"vm", "lxc"}:
        raise _manifest_error(
            f"cluster '{cluster_name}' resource {index} type must be 'vm' or 'lxc'"
        )

    node = resource.get("node")
    if not isinstance(node, str) or not node.strip():
        raise _manifest_error(f"cluster '{cluster_name}' resource {index} node must be set")

    vmid = resource.get("vmid")
    if isinstance(vmid, bool) or not isinstance(vmid, int):
        raise _manifest_error(f"cluster '{cluster_name}' resource {index} vmid must be an integer")
    if vmid <= 0:
        raise _manifest_error(f"cluster '{cluster_name}' resource {index} vmid must be positive")

    return resource


def _validate_cluster(cluster: Any, index: int) -> dict[str, Any]:
    if not isinstance(cluster, dict):
        raise _manifest_error(f"cluster {index} must be a mapping")

    name = _non_empty_string(cluster.get("name"), f"cluster {index} name")
    api_url = _non_empty_string(cluster.get("api_url"), f"cluster '{name}' api_url")

    resources = cluster.get("resources")
    if not isinstance(resources, list):
        raise _manifest_error(f"cluster '{name}' resources must be a list")

    cluster["name"] = name
    cluster["api_url"] = api_url
    cluster["resources"] = [_validate_resource(resource, name, resource_index) for resource_index, resource in enumerate(resources)]
    return cluster


def _normalize_api_url(api_url: str) -> str:
    parsed = urlsplit(api_url if "://" in api_url else f"//{api_url}", scheme="https")
    if not parsed.netloc:
        raise ValueError("api_url must include a host")
    if parsed.scheme and parsed.scheme != "https":
        raise ValueError("api_url must use https")
    if parsed.username or parsed.password:
        raise ValueError("api_url must not include userinfo")
    if parsed.query or parsed.fragment:
        raise ValueError("api_url must not include query or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("api_url must not include a path")
    if parsed.port is not None and parsed.port != 8006:
        raise ValueError("api_url port must be 8006")

    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("api_url must include a host")

    return f"https://{hostname}:8006/api2/json"


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)

    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be a mapping")

    clusters = manifest.get("clusters")
    if not isinstance(clusters, list):
        raise ValueError("manifest clusters must be a list")
    if not clusters:
        raise ValueError("manifest must contain at least one cluster")

    normalized_clusters: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, cluster in enumerate(clusters):
        normalized = _validate_cluster(cluster, index)
        if normalized["name"] in seen_names:
            raise ValueError(f"duplicate cluster name '{normalized['name']}'")
        seen_names.add(normalized["name"])
        normalized["api_url"] = _normalize_api_url(normalized["api_url"])
        normalized_clusters.append(normalized)

    manifest["clusters"] = normalized_clusters
    return manifest


def select_cluster(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    cluster_name = _non_empty_string(name, "cluster name")
    clusters = manifest.get("clusters")
    if not isinstance(clusters, list):
        raise ValueError("manifest clusters must be a list")

    matched = [cluster for cluster in clusters if isinstance(cluster, dict) and cluster.get("name") == cluster_name]
    if not matched:
        raise ValueError(f"cluster '{cluster_name}' not found")
    if len(matched) > 1:
        raise ValueError(f"duplicate cluster name '{cluster_name}'")
    return matched[0]


def resource_endpoint(resource_type: str, node: str, vmid: int) -> str:
    segment = {"vm": "qemu", "lxc": "lxc"}.get(resource_type)
    if segment is None:
        raise ValueError("resource type must be 'vm' or 'lxc'")
    _non_empty_string(node, "node")
    if isinstance(vmid, bool) or not isinstance(vmid, int):
        raise ValueError("vmid must be an integer")
    return f"/nodes/{quote(node, safe='')}/{segment}/{vmid}"


class ProxmoxClient:
    def __init__(self, api_url: str, token_id: str, token_secret: str, *, insecure: bool = False):
        self.api_url = _normalize_api_url(_non_empty_string(api_url, "api_url"))
        self.token_id = _non_empty_string(token_id, "token_id")
        self.token_secret = _non_empty_string(token_secret, "token_secret")
        self.insecure = insecure

    def request(self, method: str, path: str, data: dict | None = None) -> dict[str, Any]:
        request_method = _non_empty_string(method, "method").upper()
        request_path = _non_empty_string(path, "path")
        if not request_path.startswith("/"):
            request_path = f"/{request_path}"

        url = f"{self.api_url}{request_path}"
        headers = {"Authorization": f"PVEAPIToken={self.token_id}={self.token_secret}"}

        body = None
        if data is not None:
            encoded = []
            for key, value in data.items():
                if isinstance(value, bool):
                    encoded.append((key, "1" if value else "0"))
                else:
                    encoded.append((key, str(value)))
            body = "&".join(
                f"{quote(str(key), safe='')}={quote(str(value), safe='')}" for key, value in encoded
            ).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        request = Request(url, data=body, headers=headers, method=request_method)
        context = ssl._create_unverified_context() if self.insecure else ssl.create_default_context()

        try:
            with urlopen(request, context=context) as response:
                payload = response.read()
        except HTTPError as error:
            body_text = ""
            try:
                body_text = error.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = ""
            status = getattr(error, "status", None) or error.code
            raise RuntimeError(
                f"{request_method} {request_path} failed with HTTP {status}: {body_text}".rstrip()
            ) from error
        except URLError as error:
            raise RuntimeError(f"{request_method} {request_path} failed: {error.reason}") from error

        try:
            decoded = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{request_method} {request_path} returned invalid JSON") from error

        if not isinstance(decoded, dict):
            raise RuntimeError(f"{request_method} {request_path} returned a non-mapping response")

        return decoded


sys.modules.setdefault("proxmox_crud", sys.modules[__name__])
sys.modules.setdefault("scripts.proxmox_crud", sys.modules[__name__])
