"""
The upper-level network port manager.

from .vt_netmgr import vt_netportmgr

# Define and create network object
define_and_create_network_object(network_name, params)

# Binding nodes
vt_netportmgr.operation(network_name, {"bind": {"nodes": ["host1"]}})

# Allocate port
vt_netportmgr.operation(network_name, {"allocate": {}})

# Sync port
vt_netportmgr.operation(network_name, {"sync": {}})

# Release port
vt_netportmgr.operation(network_name, {"release": {}})

# Unbind nodes
vt_netportmgr.operation(network_name, {"unbind": {"nodes": []}})

# Get the resource of network port
out = vt_netportmgr.get_network_port_info(network_name, request=None, verbose=None)
out:
{
    "meta": {
        "allocated": allocated,
    },
    "spec": {
        "switch": switch,
        "fds": tap_fd,
        "ifname": tap_ifname,
    },
}

# Destroy the network port object
vt_netportmgr.destroy_network_object(network_name)
"""

import logging

from virttest.vt_resmgr import resmgr

LOG = logging.getLogger("avocado." + __name__)


class _VTNetworkPortManager(object):
    def __init__(self):
        self._res_config = dict()
        self._resource_id = dict()

    def define_and_create_network_object(self, network_name, params, net_type="port"):
        """
        Define network port configuration and create the network port object.

        :param network_name: the network name.
        :type network_name: string
        :param params: the related params from cluster.json
        :type params: dict
        :param net_type: net type
        :type net_type: string

        :return: network name
        :rtype: string
        """
        LOG.debug(f"Defining the network configuration for {network_name}")
        self._res_config[network_name] = resmgr.define_resource_config(
            network_name, net_type, params
        )
        LOG.debug(f"Done to define the network configuration for {network_name}")

        LOG.debug(f"Create the network object for {network_name}")
        self._resource_id[network_name] = resmgr.create_resource_object(
            self._res_config[network_name]
        )
        LOG.debug(f"Done to create the network object for {network_name}")
        return network_name

    def destroy_network_object(self, network_name):
        """
        Destroy the network port object.

        :param network_name: the network name.
        :type network_name: string
        """
        LOG.debug(f"Destroy the network object {network_name}")
        self._resource_id[network_name] = {}
        self._res_config[network_name] = {}
        LOG.debug(f"Done to destroy the network object {network_name}")

    def operation(self, network_name, operation_params):
        resmgr.update_resource(self._resource_id[network_name], operation_params)

    def query_all_network_names(self):
        """
        Return all network names.

        :return: All network names.
        :rtype: list
        """
        return list(self._resource_id.keys())

    def get_network_port_info(self, network_name, request=None, verbose=None):
        """
        Return the related resource info.

        :return: the resource info of network_name.
        :rtype: dict
        """
        return resmgr.get_resource_info(
            self._resource_id[network_name], request, verbose
        )


vt_netportmgr = _VTNetworkPortManager()
