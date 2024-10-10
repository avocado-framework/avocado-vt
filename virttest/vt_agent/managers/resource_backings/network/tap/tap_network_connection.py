import logging


from ...pool_connection import _ResourcePoolConnection


LOG = logging.getLogger("avocado.agents.resource_backings.network.tap." + __name__)


class _TapNetworkConnection(_ResourcePoolConnection):
    _CONNECT_POOL_TYPE = "linux bridge"

    def __init__(self, pool_config):
        super().__init__(pool_config)
        spec = pool_config["spec"]
        pass

    def open(self):
        # TODO
        pass

    def close(self):
        # TODO
        pass

    def connected(self):
        # TODO
        return False
