import logging


from ...pool import _ResourcePool
from .tap_port import get_port_resource_class

from virttest.data_dir import get_shared_dir
from virttest.utils_misc import generate_random_string
from virttest.vt_cluster import cluster


LOG = logging.getLogger("avocado." + __name__)


class _LinuxBridgeNetwork(_ResourcePool):
    _POOL_TYPE = "linux_bridge"

    @classmethod
    def define_config(cls, pool_name, pool_params):
        # config = super().define_config(pool_name, pool_params)
        # config["spec"].update(
        #     {
        #         "server": pool_params["nfs_server_ip"],
        #         "export": pool_params["nfs_mount_src"],
        #         "mount-options": pool_params.get("nfs_mount_options"),
        #         "mount": pool_params.get("nfs_mount_dir",
        #                                  os.path.join(get_shared_dir(), generate_random_string(6)))
        #     }
        # )
        # return config
        pass

    def get_resource_class(cls, resource_type):
        pass

    def meet_resource_request(self, resource_type, resource_params):
        pass
