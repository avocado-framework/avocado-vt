import logging

from virttest.vt_utils.net import interface, tap
from virttest.vt_utils.net.drivers import bridge

from ...backing import _ResourceBacking

LOG = logging.getLogger("avocado.agents.resource_backings.network.tap" + __name__)


class _TapPortBacking(_ResourceBacking):
    _SOURCE_POOL_TYPE = "tap"
    _BINDING_RESOURCE_TYPE = "port"

    def __init__(self, backing_config):
        super().__init__(backing_config)
        self.switch = None
        self.tap_fd = None

    def create(self, network_connection):
        if not self.switch:
            self.switch = network_connection.ifname

    def destroy(self, network_connection):
        super().destroy(network_connection)
        self.switch = None

    def allocate_resource(self, network_connection, arguments=None):
        """
        Create a tap device and put this device in to network_connection.

        :params network_connection: the _TapNetworkConnection object.
        :type network_connection: class _TapNetworkConnection.
        :params arguments: the device's params as following:
                            {
                                "ifname": xxx,
                            }
        :type arguments: dict.

        :return: the tap file descriptor.
        :rtype: int.
        """
        self.tap_fd = tap.open_tap("/dev/net/tun", arguments["ifname"], vnet_hdr=True)
        interface.bring_up_ifname(arguments["ifname"])
        bridge.add_to_bridge(arguments["ifname"])

        return self.get_resource_info(network_connection)

    def release_resource(self, network_connection, arguments=None):
        bridge.del_from_bridge(arguments["ifname"])
        interface.bring_down_ifname(arguments["ifname"])
        self.tap_fd = None

        return self.get_resource_info(network_connection)

    def get_resource_info(self, network_connection, arguments=None):
        allocated = (
            True
            if self.switch is bridge.find_bridge_name(arguments["ifname"])
            else False
        )

        return {
            "meta": {
                "allocated": allocated,
            },
            "spec": {
                "switch": self.switch,
                "fds": self.tap_fd,
            },
        }
