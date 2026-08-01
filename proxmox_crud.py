import sys

from scripts.proxmox_crud import *  # noqa: F401,F403
from scripts import proxmox_crud as _impl

sys.modules[__name__] = _impl
sys.modules["scripts.proxmox_crud"] = _impl

