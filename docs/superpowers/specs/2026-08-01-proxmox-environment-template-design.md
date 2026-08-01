# Proxmox Environment Template and CRUD CLI Design

## Purpose

Provide a reusable Proxmox VE environment template and a Python command-line
client for managing virtual machines and LXC containers across multiple
independent clusters through the Proxmox REST API.

## Deliverables

- `docs/proxmox-environment-template.md`: a fill-in environment runbook.
- `docs/proxmox-manifest.example.yaml`: an example declarative resource
  manifest.
- `scripts/proxmox_crud.py`: a CLI supporting create, read, update, and delete
  operations.
- Targeted unit tests for manifest handling, API request construction,
  authentication, and mutation safeguards.

## Template

The Markdown template will include placeholders for environment ownership,
cluster API endpoints, nodes, storage, networks, access controls, credential
references, operational procedures, and client integration details. Its
cluster inventory uses repeatable table rows so it can document one or many
clusters without structural changes.

The REST API section explains the JSON base path
`https://<cluster-url>:8006/api2/json`, token authentication, response
handling, and asynchronous task identifiers. It provides non-secret cURL
examples that operators can adapt.

## Manifest Model

The YAML manifest contains a `clusters` collection. Each entry supplies a
unique logical cluster name, its API URL, and a `resources` collection. Each
resource declares `type` as `vm` or `lxc`, the target node, VMID, desired
attributes, and optional creation-only attributes.

The CLI selects a cluster by logical name; it does not assume clusters share
credentials, nodes, storage, VMIDs, or network definitions. API token
credentials are loaded from `PROXMOX_API_TOKEN_ID` and
`PROXMOX_API_TOKEN_SECRET`, never from the manifest.

## CLI Behavior

`create` and `update` accept a YAML document and operate on selected resources.
`read` and `delete` accept explicit cluster, node, resource type, and VMID
arguments. The script invokes the Proxmox REST API directly using Python's
standard library and sends the appropriate VM or LXC endpoint requests.

Mutation commands support `--dry-run`. Deletion requires `--confirm`. TLS
certificate verification is enabled by default; an explicit opt-out is
available only for development environments. API errors and malformed
documents produce descriptive stderr output and a non-zero exit status.

## Validation

Tests mock the HTTP transport and cover URL construction, API-token headers,
cluster and resource selection, VM/LXC CRUD calls, dry-run behavior, and
delete confirmation. Documentation examples will align with the accepted
manifest shape and CLI flags.

## Out of Scope

- Managing Proxmox cluster membership, nodes, storage, or network lifecycle.
- Persisting state outside of the source manifest.
- Supporting resources beyond VMs and LXC containers.
- Embedding or storing secrets in documentation or manifests.
