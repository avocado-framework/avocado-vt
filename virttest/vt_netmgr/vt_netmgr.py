"""
The upper-level network port manager.

from .vt_netmgr import vt_netportmgr

# Define the network port object
define_network_port_object(nic_name, params)

# Create the network port object
create_network_port_object(network_port_id)

# Binding nodes
vt_netportmgr.operation(network_port_id, {"bind": {"nodes": ["host1"]}})

# Allocate port
vt_netportmgr.operation(network_port_id, {"allocate": {}})

# Sync port
vt_netportmgr.operation(network_port_id, {"sync": {}})

# Release port
vt_netportmgr.operation(network_port_id, {"release": {}})

# Unbind nodes
vt_netportmgr.operation(network_port_id, {"unbind": {"nodes": []}})

# Get the resource of network port
out = vt_netportmgr.get_network_port_info(network_port_id, request=None, verbose=None)
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
vt_netportmgr.destroy_network_object(network_port_id)
"""

import logging
import uuid

from virttest.vt_resmgr import resmgr

LOG = logging.getLogger("avocado." + __name__)


class _VTNetworkPortManager(object):
    def __init__(self):
        self._res_config = dict()
        self._resource_id = dict()

    def define_network_port_object(self, nic_params, vm_node):
        """
        Define network port configuration.

        :param nic_params: the params of nic
        :type nic_params: dict
        :parsm vm_node: the node allowed accessing
        :type vm_node: string

        :return: resource config
        :rtype: dict
        """
        network_port_id = uuid.uuid4().hex
        nic_params["vm_node"] = vm_node
        LOG.debug(f"Defining the network port configuration for {network_port_id}")
        self._res_config[network_port_id] = resmgr.define_resource_config(
            network_port_id, "port", nic_params
        )
        LOG.debug(
            f"Done to define the network port configuration for {network_port_id}"
        )
        return network_port_id

    def create_network_port_object(self, network_port_id):
        """
        Create the network port object.

        :param network_port_id: the network port id. The format is ${pool_id}.${nic_name}
        :type network_port_id: string

        :return: network_port_id
        :rtype: string
        """
        LOG.debug(f"Create the network port object for {network_port_id}")
        self._resource_id[network_port_id] = resmgr.create_resource_object(
            self._res_config[network_port_id]
        )
        LOG.debug(f"Done to create the network port object for {network_port_id}")
        return network_port_id

    def destroy_network_port_object(self, network_port_id):
        """
        Destroy the network port object.

        :param network_port_id: the network port id. The format is ${pool_id}.${nic_name}
        :type network_port_id: string
        """
        LOG.debug(f"Destroy the network port object {network_port_id}")
        self._resource_id[network_port_id] = {}
        self._res_config[network_port_id] = {}
        LOG.debug(f"Done to destroy the network port object {network_port_id}")

    def operation(self, network_name, operation_params):
        resmgr.update_resource(self._resource_id[network_name], operation_params)

    def query_all_network_ports_name(self):
        """
        Return all network names.

        :return: All network names.
        :rtype: list
        """
        return list(self._resource_id.keys())

    def get_network_port_info(self, network_port_id, request=None, verbose=None):
        """
        Return the related resource info.

        :param network_port_id: the network port id. The format is ${pool_id}.${nic_name}
        :type network_port_id: string
        :param request: The query content, format:
                          None
                          meta[.<key>]
                          spec[.<key>]
                        Examples:
                          meta
                          spec.size
        :type request: string
        :param verbose: True to get the resource pool's configuration, while
                        False to get the resource pool's uuid
        :type verbose: boolean

        :return: the resource info of network_name.
        :rtype: dict
        """
        return resmgr.get_resource_info(
            self._resource_id[network_port_id], request, verbose
        )


vt_netportmgr = _VTNetworkPortManager()
