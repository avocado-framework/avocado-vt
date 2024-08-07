import logging

from ...pool import _ResourcePool
from .nfs_resources import get_nfs_resource_class


LOG = logging.getLogger("avocado." + __name__)


# Configure two nfs pools
#[nfs_pool1]
#pool_type = "nfs"
#pool_access_nodes = "node1 node2"
#pool_nfs_server =
#pool_nfs_export =
#pool_nfs_mount =
#pool_nfs_mount_options =

class _NfsPool(_ResourcePool):
    _POOL_TYPE = "nfs"

    @classmethod
    def define_config(cls, pool_name, pool_params):
        config = super().define_config(pool_name, pool_params)
        config["spec"].update({
            "server": pool_params["server"],
            "export": pool_params["export"],
            "mount": pool_params["mount"],
            "mount-options": pool_params.get("mount_options"),
        }

    @classmethod
    def get_resource_class(cls, resource_type):
        return get_nfs_resource_class(resource_type)

    def meet_resource_request(self, resource_type, resource_params):
        # Specify a pool
        pool_tag = resource_params.get("image_pool_name")
        if pool_tag:
            partition_id = resource_params.get("cluster_partition_uuid")
            pool_id = cluster.get_partition(partition_id).pools.get(pool_tag)
            return True if pool_id == self.pool_id else False

        # Check if this is the pool with the specified type
        if resource_params.get("storage_type") != self.get_pool_type():
            return False

        # Check if the pool can supply a resource with a specified type
        if not self.get_resource_class(resource_type):
            return False

        # TODO: Check if the pool has capacity to allocate the resource
        return True
