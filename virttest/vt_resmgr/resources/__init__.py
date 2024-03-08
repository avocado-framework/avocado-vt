from .storage import _DirPool, _NfsPool

_pool_classes = dict()
_pool_classes[_DirPool.get_pool_type()] = _DirPool
_pool_classes[_NfsPool.get_pool_type()] = _NfsPool


def get_resource_pool_class(pool_type):
    return _pool_classes.get(pool_type)


__all__ = ["get_resource_pool_class"]
