"""Package for vm network management."""

from typing import Type

from virttest.utils_env import Env
from virttest.utils_params import Params

from .interface import VMInterface
from .netconfig import VMNetconfig
from .network import VMNetwork
from .node import VMNode
from .tunnel import VMTunnel


def setup_vmnet(
    params: Params, env: Env, network_class: Type[VMNetwork] = VMNetwork
) -> VMNetwork:
    """Attach and prepare a VM network without retrieving object states."""
    vmnet = env.get_vmnet()
    if vmnet is not None:
        return vmnet

    env.start_ip_sniffing(params)
    vmnet = network_class(params, env)
    vmnet.setup_host_bridges()
    vmnet.setup_host_services()
    env.register_vmnet(vmnet)
    return vmnet
