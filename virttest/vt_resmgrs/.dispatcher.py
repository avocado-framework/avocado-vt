from .storage.dir import _dir_pool_mgr
from .storage.nbd import _nbd_pool_mgr
from .storage.nfs import _nfs_pool_mgr
from .storage.ceph import _ceph_pool_mgr
from .storage.iscsi_direct import _iscsi_direct_pool_mgr


RESOURCE_MANAGERS = dict()
RESOURCE_MANAGERS[_dir_pool_mgr.POOL_TYPE] = resmgr

    def register_resmgr(self, resmgr):

    def dispatch_resmgr(self, pool_type):
        return self.RESOURCE_MANAGERS.get(pool_type)

    def dispatch_pool(self, resource_id):
        for resmgr in self.RESOURCE_ANAGERS.values():
            for pool in resmgr.pools:
                if resource_id in pool.resources:
                    return pool
        return None


dispatcher = _Dispatcher()
dispatcher.register_resmgr(_dir_resmgr)
dispatcher.register_resmgr(_nbd_resmgr)
dispatcher.register_resmgr(_nfs_resmgr)
dispatcher.register_resmgr(_ceph_resmgr)
dispatcher.register_resmgr(_iscsi_direct_resmgr)
