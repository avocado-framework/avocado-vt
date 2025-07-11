import logging

from virttest.vt_utils.net import interface
from virttest.vt_utils.net.drivers import bridge

from ...pool_connection import _ResourcePoolConnection

LOG = logging.getLogger("avocado.service." + __name__)


class _TapNetworkConnection(_ResourcePoolConnection):
    _CONNECT_POOL_TYPE = "linux_bridge"

    def __init__(self, pool_config):
        super().__init__(pool_config)
        self._switch = pool_config["spec"]["switch"]
        self._export = pool_config["spec"]["export"]

    def open(self):
        # TODO
        pass

    def close(self):
        # TODO
        pass

    @property
    def connected(self):
        if_info = interface.net_get_iface_info(self._switch)
        if (
            if_info[0]
            and if_info[0]["operstate"] in ("UP",)
            and (
                bridge.find_bridge_name(self._export) in (self._switch,)
                or self._export is ""
            )
        ):
            return True
        return False

    @property
    def switch(self):
        return self._switch

    @property
    def export(self):
        return self._export
