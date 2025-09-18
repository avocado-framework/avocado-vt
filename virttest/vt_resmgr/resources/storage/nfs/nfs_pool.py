import logging
import os

from virttest.data_dir import get_shared_dir
from virttest.utils_misc import generate_random_string
from virttest.vt_cluster import cluster

from ...pool import _ResourcePool, _PoolSelector
from .nfs_volume import _NfsFileVolume

LOG = logging.getLogger("avocado." + __name__)


class _NfsPool(_ResourcePool):
    _POOL_TYPE = "nfs"
    _SUPPORTED_RESOURCE_CLASSES = {
        "volume": _NfsFileVolume,
    }

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

    def meet_conditions(self, condition_params):
        """
        Check if the pool can meet the conditions
        """
        selectors = condition_params.get("volume_pool_selectors", list())
        if not selectors:
            # Add the storage pool type
            storage_type = resource_params.get("storage_type")
            if storage_type:
                selectors.append(
                    {
                        "key": "type",
                        "operator": "==",
                        "values": storage_type,
                    }
                )

        return  _PoolSelector(selectors).match(self)
