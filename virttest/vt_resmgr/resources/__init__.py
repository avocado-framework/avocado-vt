from .storage import _DirPool

_pool_classes = dict()
_pool_classes[_DirPool.get_pool_type()] = _DirPool


def get_pool_class(pool_type):
    return _pool_classes.get(pool_type)


__all__ = ["get_pool_class"]
