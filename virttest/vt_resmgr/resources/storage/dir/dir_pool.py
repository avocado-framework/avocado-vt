import logging

from ...pool import _ResourcePool
from ...pool_selector import _PoolSelector
from .dir_volume import _DirFileVolume

LOG = logging.getLogger("avocado." + __name__)


class _DirPool(_ResourcePool):
    _POOL_TYPE = "filesystem"
    _SUPPORTED_RESOURCE_CLASSES = {
        "volume": _DirFileVolume,
    }

    @classmethod
    def define_default_config(cls, node_names):
        """
        We'll define a default filesystem pool if it is not defined
        """
        pool_name = "default_dir_pool"
        pool_params = {
            "type": cls._POOL_TYPE,
            "path": "",  # Let the worker node use a default path
            "access": {
                "nodes": node_names,
            },
        }
        return cls.define_config(pool_name, pool_params)

    @classmethod
    def define_config(cls, pool_name, pool_params):
        config = super().define_config(pool_name, pool_params)

        # The path could be "" or a relative path, make up an abspath
        # on the worker node when attaching the dir pool
        config["spec"]["path"] = pool_params.get("path", "")
        return config

    def attach(self, node):
        r, o = super().attach(node)

        # The local path can be finalized only when attaching it to a node
        self.pool_spec["path"] = o["out"]["spec"]["path"]
        return r, o

    def meet_conditions(self, conditions):
        """
        Check if the pool can meet the conditions
        """
        selectors = conditions.get("volume_pool_selectors", list())
        if not selectors:
            # Add the storage pool type
            storage_type = conditions.get("storage_type")
            if storage_type:
                selectors.append(
                    {
                        "key": "type",
                        "operator": "==",
                        "values": storage_type,
                    }
                )

        return _PoolSelector(str(selectors)).match(self)
