"""
The upper-level network manager.

from virttest.vt_netgr import vt_netmgr
"""
import logging

from virttest.vt_cluster import cluster
from virttest.vt_resmgr.resources.network import network as nt

LOG = logging.getLogger("avocado." + __name__)


class _VTNetworkManager(object):
    """
    The Network Manager.
    """

    def __init__(self):
        self._networks = list()
        self._ports = list()

    def startup(self):
        LOG.info(f"Start the network manager!")

    def teardown(self):
        LOG.info(f"Stop the network manager!")

    def create_network(self, network_name, params):
        """
        Create the network by its cartesian params.

        :param network_name: The network tag defined in cartesian params.
        :type network_name: String.
        :param params: The params for all the network.
        :type params: Dict.
        """
        network_obj = nt(network_name, params)
        network_obj.create()
        self._networks.append(network_obj)

    def delete_network(self, descriptor):
        """
        Delete the networks by its descriptor.

        :param descriptor: The network name or the uuid.
        :type descriptor: String.
        """
        be_deleted = []
        for obj in self._networks:
            if descriptor in (obj.uuid, obj.name, ):
                obj.delete()
                be_deleted.append(obj)

        for obj in be_deleted:
            self._networks.remove(obj)

    def get_networks(self, descriptor):
        """
        Filter the networks based on the descriptor.
        NOTE: return all networks if descriptor is None.

        :param descriptor: The network name or the uuid.
        :type descriptor: String.
        """
        if not descriptor:
            return self._networks
        res = []
        for obj in self._networks:
            if descriptor in (obj.uuid, obj.name, ):
                res.append(obj)
        return res
