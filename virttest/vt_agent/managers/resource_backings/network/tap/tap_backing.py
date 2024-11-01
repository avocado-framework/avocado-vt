import logging


from ...backing import _ResourceBacking


LOG = logging.getLogger("avocado.agents.resource_backings.network.tap" + __name__)


class _TapPortBacking(_ResourceBacking):
    _SOURCE_POOL_TYPE = "tap"
    _BINDING_RESOURCE_TYPE = "port"

    def __init__(self, backing_config):
        super().__init__(backing_config)
        pass

    def create(self, pool_connection):
        pass

    def destroy(self, pool_connection):
        pass

    def allocate_resource(self, pool_connection, arguments):
        raise NotImplemented

    def release_resource(self, pool_connection, arguments):
        raise NotImplemented

    def get_resource_info(self, pool_connection):
        pass

    def sync_resource(self, pool_connection, arguments):
        raise NotImplemented
