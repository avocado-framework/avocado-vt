# from .cvm import _SnpPool
# from .cvm import _TdxPool
# from .storage import _CephPool
from .storage import _DirPool, _NfsPool
from .network import _LinuxBridgeNetwork

_pool_classes = dict()
# _pool_classes[_SnpPool.get_pool_type()] = _SnpPool
# _pool_classes[_TdxPool.get_pool_type()] = _TdxPool
# _pool_classes[_CephPool.get_pool_type()] = _CephPool
_pool_classes[_DirPool.get_pool_type()] = _DirPool
_pool_classes[_NfsPool.get_pool_type()] = _NfsPool
_pool_classes[_LinuxBridgeNetwork.get_pool_type()] = _LinuxBridgeNetwork


def get_resource_pool_class(pool_type):
    return _pool_classes.get(pool_type)


__all__ = ["get_resource_pool_class"]
