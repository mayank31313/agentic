import os

from fastmcp.tools import tool
from proxmoxer import ProxmoxAPI

def get_proxmox_tools():
    host = os.getenv("PROXMOX_HOST")
    user = os.getenv("PROXMOX_USER")
    token_name = os.getenv("PROXMOX_TOKEN_NAME")
    token_value = os.getenv("PROXMOX_TOKEN_VALUE")
    verify_ssl=os.environ.get("PROXMOX_VERIFY_SSL", "false").lower() == "true"

    proxmox_client = ProxmoxAPI(
        host=host,
        user=user,
        token_name=token_name,
        token_value=token_value,
        verify_ssl=verify_ssl
    )

    @tool
    def list_proxmox_nodes():
        """List all nodes in the Proxmox cluster."""
        nodes = proxmox_client.nodes.get()
        return [node['node'] for node in nodes]

    @tool
    def list_proxmox_vms(node_name: str):
        """List all VMs on a specific Proxmox node."""
        vms = proxmox_client.nodes(node_name).qemu.get()
        return [vm['name'] for vm in vms]

    @tool
    def get_proxmox_vm_status(node_name: str, vm_id: int):
        """Get the status of a specific VM on a Proxmox node."""
        status = proxmox_client.nodes(node_name).qemu(vm_id).status.current.get()
        return status

    @tool
    def start_proxmox_vm(node_name: str, vm_id: int):
        """Start a specific VM on a Proxmox node."""
        proxmox_client.nodes(node_name).qemu(vm_id).status.start.post()
        return f"VM {vm_id} on node {node_name} started."

    @tool
    def stop_proxmox_vm(node_name: str, vm_id: int):
        """Stop a specific VM on a Proxmox node."""
        proxmox_client.nodes(node_name).qemu(vm_id).status.stop.post()
        return f"VM {vm_id} on node {node_name} stopped."


    return [list_proxmox_nodes, list_proxmox_vms, get_proxmox_vm_status]