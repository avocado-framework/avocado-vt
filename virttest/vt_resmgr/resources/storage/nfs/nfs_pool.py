import logging
import os

from virttest.data_dir import get_shared_dir
from virttest.utils_misc import generate_random_string
from virttest.vt_cluster import cluster

from ...pool import _ResourcePool
from .nfs_resources import get_nfs_resource_class

LOG = logging.getLogger("avocado." + __name__)


class _NfsPool(_ResourcePool):
    _POOL_TYPE = "nfs"

    @classmethod
    def define_config(cls, pool_name, pool_params):
        config = super().define_config(pool_name, pool_params)
        config["spec"].update(
            {
                "server": pool_params["nfs_server"],
                "export": pool_params["nfs_export_dir"],
                "mount-options": pool_params.get("nfs_mount_options"),
                # TODO: Let the agent choose the mnt if nfs_mount_point is not set
                "mount": pool_params.get(
                    "nfs_mount_point",
                    os.path.join(get_shared_dir(), generate_random_string(6)),
                ),
            }
        )
        return config

    @classmethod
    def get_resource_class(cls, resource_type):
        return get_nfs_resource_class(resource_type)

    def meet_resource_request(self, resource_type, resource_params):
        """
        Check if the pool can satisfy the resource's requirements
        """
        # Check if the pool can support a specific resource type
        if not self.get_resource_class(resource_type):
            return False

        # Note if you want the image is created from a specific pool or
        # the image is handled on a specific worker node, you should
        # specify its image_pool_name
        binding_nodes = self.get_binding_nodes(resource_params.get("vm_node"))
        if not binding_nodes:
            return False

        # Specify a storage pool name
        # Just return the pool without any more checks
        pool_tag = resource_params.get("image_pool_name")
        if pool_tag:
            pool_id = cluster.partition.pools.get(pool_tag)
            return True if pool_id == self.pool_id else False

        # Specify a storage pool type
        # Do more checks to select one from the pools with the same type
        storage_type = resource_params.get("storage_type")
        if storage_type:
            if storage_type != self.get_pool_type():
                return False

        return True
