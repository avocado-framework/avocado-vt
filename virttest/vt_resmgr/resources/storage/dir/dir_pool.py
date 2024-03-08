import os
import logging

from ...pool import _ResourcePool
from .dir_resources import get_dir_resource_class

from virttest.data_dir import get_data_dir
from virttest.vt_cluster import cluster


LOG = logging.getLogger("avocado." + __name__)


class _DirPool(_ResourcePool):
    _POOL_TYPE = "filesystem"
    _POOL_DEFAULT_DIR = "/home/kvm_autotest_root"

    def __init__(self, pool_config):
        super().__init__(pool_config)

    @classmethod
    def define_default_config(cls):
        pool_name = "dir_pool_default"
        pool_params = {
            "type": cls._POOL_TYPE,
            "path": cls._POOL_DEFAULT_DIR,
            "access": {
                "nodes": list(),
            }
        }
        return cls.define_config(pool_name, pool_params)

    @classmethod
    def define_config(cls, pool_name, pool_params):
        config = super().define_config(pool_name, pool_params)
        path = pool_params.get("path") or os.path.join(get_data_dir(), "images")
        config["spec"]["path"] = path
        return config

    @classmethod
    def get_resource_class(cls, resource_type):
        return get_dir_resource_class(resource_type)

    def meet_resource_request(self, resource_type, resource_params):
        partition_id = resource_params.get("cluster_partition_uuid")

        # Specify a pool
        pool_tag = resource_params.get("image_pool_name")
        if pool_tag:
            pool_id = cluster.get_partition(partition_id).pools.get(pool_tag)
            return True if pool_id == self.pool_id else False

        # Check if this is the pool with the specified type
        if resource_params.get("storage_type", "filesystem") != self.get_pool_type():
            return False

        # FIXME: Check if the pool can be accessed by the partition or vm nodes
        node_names = [node.name for node in cluster.get_partition(partition_id).nodes]
        if not set(self.attaching_nodes).intersection(set(node_names)):
            return False

        # Check if the pool can supply a resource with a specified type
        if not self.get_resource_class(resource_type):
            return False

        # TODO: Check if the pool has capacity to allocate the resource
        return True
