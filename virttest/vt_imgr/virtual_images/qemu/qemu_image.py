import copy
import logging

from virttest.vt_resmgr import resmgr
from virttest.utils_misc import generate_random_string

from ..image import _Image

LOG = logging.getLogger("avocado." + __name__)


class _QemuImage(_Image):
    """
    The qemu image
    """

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        config = super()._define_config_legacy(image_name, image_params)
        volume_config = resmgr.define_resource_config(
            image_name, "volume", image_params
        )

        if image_params.get("vm_node"):
            nodes = [image_params["vm_node"]]

        config["spec"].update(
            {
                "backing": None,
                "volume_config": volume_config,
            }
        )

        return config

    def keep(self):
        pass

    def create(self, arguments):
        self.allocate_volume(arguments)

    def destroy(self, arguments):
        self.release_volume(arguments)

    def create_object_from_self(self, image_pool_id=None):
        if image_pool_id is None:
            d = resmgr.get_resource_info(self.volume_id, "meta.pool")
            image_pool_id = d["pool"]

        postfix = generate_random_string(8)
        config = copy.deepcopy(self.image_config)
        config["meta"].update(
            {
                "name": f"{self.image_name}_{postfix}",
            }
        )
        config["spec"].update(
            {
                "backing": None,
                "backup": None,
                "volume": resmgr.create_resource_object_from(self.volume_id, image_pool_id),
            }
        )
        return self.__class__(config)

    def create_object(self):
        LOG.debug(f"Create the qemu image object for {self.image_name}")
        volume_config = self.image_spec.pop("volume_config")
        volume_id = resmgr.create_resource_object(volume_config)
        resmgr.update_resource(volume_id, {"bind": {}})
        self.image_spec["volume"] = volume_id

    def destroy_object(self):
        LOG.debug(f"Destroy the qemu image object for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"unbind": dict()})
        resmgr.destroy_resource_object(self.volume_id)

    def sync_volume_info(self, arguments):
        LOG.debug(f"Sync up the volume conf for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"sync": arguments})

    def bind_volume(self, arguments):
        LOG.debug(f"Bind the volume to {arguments.get('nodes')}")
        resmgr.update_resource(self.volume_id, {"bind": arguments})

    def allocate_volume(self, arguments):
        LOG.debug(f"Allocate the volume for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"allocate": arguments})

    def release_volume(self, arguments):
        LOG.debug(f"Release the volume for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"release": arguments})
