from .pool_collections import PoolCollections


class _VTResourceManager(object):
    _POOL_CLASSES = dict()

    def __init__(self):
        self._pools = dict() # {pool id: pool object}

    @classmethod
    def _get_pool_class(cls, pool_type):
        return cls._POOL_CLASSES.get(pool_type)

    def initialize(self, pool_config_list):
        for config in pool_config_list:
            pool_id = self.register_pool(config)
            self.attach_pool(pool_id)

    def deinitialize(self):
        for pool_id in self.pools:
            self.unregister_pool(pool_id)

    def get_pool_by_name(self, pool_name):
        pools = [p for p in self.pools.values() if p.pool_name == pool_name]
        return pools[0] if pools else None

    def get_pool_by_id(self, pool_id):
        return self.pools.get(pool_id, None)

    def get_pool_by_resource(self, resource_id):
        pools = [p for p in self.pools.values() if resource_id in p.resources]
        return pools[0] if pools else None

    def register_pool(self, pool_config):
        pool_type = pool_config['type']
        pool_class = PoolCollections.get_pool_class(pool_type)
        pool = pool_class(pool_config)
        self._pools[pool.pool_id] = pool
        return pool.pool_id

    def unregister_pool(self, pool_id):
        """
        The pool should be detached from all worker nodes
        """
        pool = self.pools[pool_id]
        self.detach_pool(pool_id)
        del(self._pools[pool_id])

    def attach_pool_to(self, pool, node):
        """
        Attach a pool to a specific node
        """
        access_config = pool.attaching_nodes[node.node_id]
        node.proxy.create_pool_connection(pool.config, access_config)

    def attach_pool(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        for node_id in pool.attaching_nodes:
            node = get_node(node_id)
            self.attach_pool_to(pool, node)

    def detach_pool_from(self, pool, node):
        """
        Detach a pool from a specific node
        """
        node.proxy.destroy_pool_connection(pool.pool_id)

    def detach_pool(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        for node_id in pool.attaching_nodes:
            node = get_node(node_id)
            self.detach_pool_from(pool, node)

    def info_pool(self, pool_id):
        """
        Get the pool's information, including 'meta' and 'spec':
        meta:
          e.g. version for tdx, 1.0 or 1.5
        spec:
          common specific attributes
            e.g. nfs_server for nfs pool
          node-specific attributes
            e.g. [node1:{path:/mnt1,permission:rw}, node2:{}]
        """
        info = dict()
        pool = self.get_pool_by_id(pool_id)
        info.update(pool.config)
        for node_id in pool.attaching_nodes:
            node = get_node(node_id)
            access_info = node.proxy.get_pool_connection(pool_id)
            info.update(access_info)

    def pool_capability(self, pool_id):
        pool = self.get_pool_by_id(pool_id)
        return pool.capability

    @property
    def pools(self):
        return self._pools


vt_resmgr = _VTResourceManager()
