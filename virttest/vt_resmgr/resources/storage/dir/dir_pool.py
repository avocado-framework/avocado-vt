import logging
import os

from virttest.data_dir import get_data_dir
from virttest.vt_cluster import cluster

from ...pool import _ResourcePool, _PoolSelector
from .dir_volume import _DirFileVolume

LOG = logging.getLogger("avocado." + __name__)


class _DirPool(_ResourcePool):
    _POOL_TYPE = "filesystem"
    _POOL_DEFAULT_DIR = "/home/kvm_autotest_root"
    _SUPPORTED_RESOURCE_CLASSES = {
        "volume": _DirFileVolume,
    }

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

    def meet_conditions(self, conditions):
        """
        Check if the pool can meet the conditions
        """
        selectors = conditions.get("volume_pool_selectors", list())
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
