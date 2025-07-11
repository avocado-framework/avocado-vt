import logging

from virttest import utils_misc
from virttest.vt_utils.net import interface, tap
from virttest.vt_utils.net.drivers import bridge

from ...backing import _ResourceBacking

LOG = logging.getLogger("avocado.service." + __name__)


class _TapPortBacking(_ResourceBacking):
    _SOURCE_POOL_TYPE = "linux_bridge"
    _BINDING_RESOURCE_TYPE = "port"

    def __init__(self, backing_config):
        super().__init__(backing_config)
        self.switch = None
        self.tap_fd = None
        self.tap_ifname = None

    def create(self, network_connection):
        if not self.switch:
            self.switch = network_connection.switch

    def destroy(self, network_connection):
        super().destroy(network_connection)
        self.switch = None

    def allocate_resource(self, network_connection, arguments=None):
        """
        Create a tap device and put this device in to network_connection.

        :params network_connection: the _TapNetworkConnection object.
        :type network_connection: class _TapNetworkConnection.
        :params arguments: the device's params
        :type arguments: dict.

        :return: the resource info.
        :rtype: dict.
        """
        if not self.tap_ifname:
            self.tap_ifname = "tap_" + utils_misc.generate_random_string(8)
        self.tap_fd = tap.open_tap("/dev/net/tun", self.tap_ifname, vnet_hdr=True)
        self.tap_fd = self.tap_fd.split(":")
        interface.bring_up_ifname(self.tap_ifname)
        bridge.add_to_bridge(self.tap_ifname, self.switch)

        return self.get_resource_info(network_connection)

    def release_resource(self, network_connection, arguments=None):
        bridge.del_from_bridge(self.tap_ifname)
        interface.bring_down_ifname(self.tap_ifname)
        self.tap_fd = None
        self.tap_ifname = None

        return self.get_resource_info(network_connection)

    def get_resource_info(self, network_connection=None, arguments=None):
        if self.switch and self.tap_fd and self.tap_ifname:
            allocated = (
                True
                if self.switch in (bridge.find_bridge_name(self.tap_ifname),)
                else False
            )
        else:
            allocated = False

        return {
            "meta": {
                "allocated": allocated,
            },
            "spec": {
                "switch": self.switch,
                "fds": self.tap_fd,
                "ifname": self.tap_ifname,
            },
        }
