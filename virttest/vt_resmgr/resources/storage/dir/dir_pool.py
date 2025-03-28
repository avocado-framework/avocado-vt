import logging
import os

from virttest.data_dir import get_data_dir
from virttest.vt_cluster import cluster

from ...pool import _ResourcePool, _PoolSelector
from .dir_resources import get_dir_resource_class

LOG = logging.getLogger("avocado." + __name__)


class _DirPool(_ResourcePool):
    _POOL_TYPE = "filesystem"
    _POOL_DEFAULT_DIR = "/home/kvm_autotest_root"

    @classmethod
    def define_default_config(cls):
        """
        We'll define a default filesystem pool if it is not defined by user
        """
        pool_name = "dir_pool_default"
        pool_params = {
            "type": cls._POOL_TYPE,
            "path": cls._POOL_DEFAULT_DIR,
            "access": {
                "nodes": list(),
            },
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

    def meet_conditions(self, conditions):
        """
        Check if the pool can meet the conditions
        """
        selectors = conditions.get("volume_pool_selectors", list())
        if not selectors:
            # Add the access nodes
            selectors.append(
                {
                    "key": "nodes",
                    "operator": "contains",
                    "values": " ".join([n.tag for n in cluster.partition.nodes]),
                }
            )

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
        return  _PoolSelector(selectors).match(pool)
