from .storage import (
    _DirPoolConnection,
    _DirVolumeBacking,
    _NfsPoolConnection,
    _NfsVolumeBacking,
)
from .network import (
    _TapPortBacking,
    _TapNetworkConnection,
)

_pool_conn_classes = dict()
_pool_conn_classes[_DirPoolConnection.get_pool_type()] = _DirPoolConnection
_pool_conn_classes[_NfsPoolConnection.get_pool_type()] = _NfsPoolConnection
_pool_conn_classes[_TapNetworkConnection.get_pool_type()] = _TapNetworkConnection

_backing_classes = dict()
_backing_classes[_DirVolumeBacking.get_pool_type()] = {
    _DirVolumeBacking.get_resource_type(): _DirVolumeBacking,
}
_backing_classes[_NfsVolumeBacking.get_pool_type()] = {
    _NfsVolumeBacking.get_resource_type(): _NfsVolumeBacking,
}
_backing_classes[_TapPortBacking.get_pool_type()] = {
    _TapPortBacking.get_resource_type(): _TapPortBacking,
}


def get_resource_backing_class(pool_type, resource_type):
    backing_classes = _backing_classes.get(pool_type, {})
    return backing_classes.get(resource_type)


def get_pool_connection_class(pool_type):
    return _pool_conn_classes.get(pool_type)


__all__ = ["get_pool_connection_class", "get_resource_backing_class"]
