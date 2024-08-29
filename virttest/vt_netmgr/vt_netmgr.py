import logging

from virttest.vt_resmgr import resmgr

LOG = logging.getLogger("avocado." + __name__)


class _VTNetworkManager(object):
    def __init__(self):
        self._res_config = dict()
        self._resource_id = dict()

    def define_and_create_network(self, network_name, params, net_type="port"):
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

        return self._resource_id[network_name]

    def operation(self, resource_id, operation_params):
        resmgr.update_resource(resource_id, operation_params)

    def query_resource_id(self, network_name):
        """
        Return all network names.

        :return: All network names.
        :rtype: list
        """
        return self._resource_id[network_name]

    def query_all_network_names(self):
        """
        Return all network names.

        :return: All network names.
        :rtype: list
        """
        return list(self._resource_id.keys())


vt_netmgr = _VTNetworkManager()
