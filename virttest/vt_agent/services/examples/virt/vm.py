"""
An example service that simulates virtual machine (VM) operations.
This is for demonstration purposes only and does not control actual VMs.
It shows how services can be organized in subdirectories.
"""

import logging
import random  # For a bit more dynamic simulation
import socket

LOG = logging.getLogger("avocado.service." + __name__)

# In a real scenario, this might hold state of simulated VMs
_simulated_vms = {}


def boot_up(vm_name="test-vm-01"):
    """
    Simulates booting up a virtual machine.

    If the VM is already 'running', it returns its current status.
    Otherwise, it 'starts' the VM and returns a success message.

    :param vm_name: The name of the VM to simulate booting.
    :type vm_name: str, optional
    :return: A dictionary containing simulation status and details.
    :rtype: dict
    """
    hostname = socket.gethostname()
    LOG.info(
        "Attempting to boot up VM '%s' on host %s (simulation).", vm_name, hostname
    )

    if vm_name in _simulated_vms and _simulated_vms[vm_name].get("status") == "running":
        LOG.info("VM '%s' is already running (simulation).", vm_name)
        return {
            "vm_name": vm_name,
            "status": "already_running",
            "host": hostname,
            "ip_address": _simulated_vms[vm_name].get("ip_address", "N/A"),
            "message": f"VM '{vm_name}' is already running.",
        }

    # Simulate assigning an IP
    simulated_ip = f"192.168.122.{random.randint(100, 200)}"
    _simulated_vms[vm_name] = {
        "status": "running",
        "ip_address": simulated_ip,
        "host": hostname,
    }

    LOG.info(
        "VM '%s' successfully booted (simulation) with IP %s.", vm_name, simulated_ip
    )
    return {
        "vm_name": vm_name,
        "status": "boot_initiated",
        "host": hostname,
        "ip_address": simulated_ip,
        "message": f"VM '{vm_name}' boot sequence initiated (simulation).",
    }


def shutdown(vm_name="test-vm-01"):
    """
    Simulates shutting down a virtual machine.

    :param vm_name: The name of the VM to simulate shutting down.
    :type vm_name: str, optional
    :return: A dictionary confirming the shutdown action.
    :rtype: dict
    """
    hostname = socket.gethostname()
    LOG.info(
        "Attempting to shut down VM '%s' on host %s (simulation).", vm_name, hostname
    )

    if vm_name in _simulated_vms and _simulated_vms[vm_name].get("status") == "running":
        _simulated_vms[vm_name]["status"] = "stopped"
        _simulated_vms[vm_name].pop("ip_address", None)  # Remove IP on shutdown
        LOG.info("VM '%s' successfully shut down (simulation).", vm_name)
        return {
            "vm_name": vm_name,
            "status": "shutdown_completed",
            "host": hostname,
            "message": f"VM '{vm_name}' has been shut down (simulation).",
        }
    elif vm_name not in _simulated_vms or (
        _simulated_vms.get(vm_name)
        and _simulated_vms[vm_name].get("status") == "stopped"
    ):
        LOG.info("VM '%s' is already stopped or does not exist (simulation).", vm_name)
        return {
            "vm_name": vm_name,
            "status": "already_stopped_or_not_found",
            "host": hostname,
            "message": f"VM '{vm_name}' was already stopped or not found.",
        }

    # Fallback for unexpected state, though ideally covered by above conditions
    LOG.warning(
        "VM '%s' in unexpected state for shutdown: %s",
        vm_name,
        _simulated_vms.get(vm_name),
    )
    return {
        "status": "unknown_error_or_not_found",
        "vm_name": vm_name,
        "message": "VM in unexpected state or not found.",
    }


def get_status(vm_name="test-vm-01"):
    """
    Simulates getting the status of a virtual machine.

    :param vm_name: The name of the VM to query.
    :type vm_name: str, optional
    :return: A dictionary containing simulated status, or 'not_found' status.
    :rtype: dict
    """
    hostname = socket.gethostname()
    LOG.info(
        "Requesting status for VM '%s' on host %s (simulation).", vm_name, hostname
    )

    if vm_name in _simulated_vms:
        status_info = _simulated_vms[vm_name]
        LOG.info("VM '%s' status: %s (simulation).", vm_name, status_info)
        return {
            "vm_name": vm_name,
            "status": status_info.get("status", "unknown"),
            "ip_address": status_info.get("ip_address"),
            # Will be None if stopped
            "host": hostname,
            "message": f"Status for VM '{vm_name}'.",
        }
    else:
        LOG.info("VM '%s' not found (simulation).", vm_name)
        return {
            "vm_name": vm_name,
            "status": "not_found",
            "host": hostname,
            "message": f"VM '{vm_name}' not found.",
        }
