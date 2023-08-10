from .storage import _NfsPool
from .storage import _NbdPool
from .storage import _CephPool
from .storage import _DirPool
from .storage import _IscsiDirectPool


class PoolCollections(object):
    _POOL_CLASSES = dict()

    @classmethod
    def register_pool_class(cls, pool_class):
        cls._POOL_CLASSES[pool_class.pool_type] = pool_class

    @classmethod
    def get_pool_class(cls, pool_type):
        return cls._POOL_CLASSES.get(pool_type)


# Register storage resource pools
PoolCollections.register_pool_class(_DirPool)
PoolCollections.register_pool_class(_NfsPool)
PoolCollections.register_pool_class(_NbdPool)
PoolCollections.register_pool_class(_CephPool)
PoolCollections.register_pool_class(_IscsiDirectPool)

# Register cvm resource pools
#PoolCollections.register_pool_class(_SevPool)
#PoolCollections.register_pool_class(_SnpPool)
#PoolCollections.register_pool_class(_TdxPool)

# Register network resource pools
#PoolCollections.register_pool_class(_VirtioNicPool)
