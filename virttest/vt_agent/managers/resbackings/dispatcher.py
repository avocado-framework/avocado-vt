from .storage import _dir_backing_mgr
from .storage import _nfs_backing_mgr
#from .storage import _ceph_backing_mgr
#from .cvm import _sev_backing_mgr
#from .cvm import _tdx_backing_mgr


class _BackingMgrDispatcher(object):

    def __init__(self):
        self._managers_mapping = dict()
        self._backings_mapping = dict()
        self._pools_mapping = dict()

    def dispatch_by_pool(self, pool_id):
        return self._pools_mapping.get(pool_id, None)

    def dispatch_by_backing(self, backing_id):
        return self._backings_mapping.get(backing_id, None)

    @classmethod
    def register(cls, mgr):
        self._managers_mapping[mgr.attached_pool_type] = mgr

    def map_pool(self, pool_id, pool_type):
        backing_mgr = self._managers_mapping[pool_type]
        self._pools_mapping[pool_id] = backing_mgr

    def unmap_pool(self, pool_id):
        del(self._pools_mapping[pool_id])

    def map_backing(self, backing_id, backing_mgr):
        self._backings_mapping[backing_id] = backing_mgr

    def unmap_backing(self, backing_id):
        del(self._backings_mapping[backing_id])


_backing_mgr_dispatcher = _BackingMgrDispatcher()

# Register storage backing managers
_backing_mgr_dispatcher.register(_dir_backing_mgr)
_backing_mgr_dispatcher.register(_nfs_backing_mgr)
#_backing_mgr_dispatcher.register(_ceph_backing_mgr)

# Register cvm backing managers
#_backing_mgr_dispatcher.register(_sev_backing_mgr)
#_backing_mgr_dispatcher.register(_tdx_backing_mgr)
