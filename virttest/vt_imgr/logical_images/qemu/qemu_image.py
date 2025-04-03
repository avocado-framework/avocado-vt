import copy
import logging

from virttest.vt_resmgr import resmgr

from ..image import _Image

LOG = logging.getLogger("avocado." + __name__)


class _QemuImage(_Image):
    """
    The lower-level qemu image
    """

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        config = super()._define_config_legacy(image_name, image_params)

        volume_config = resmgr.define_resource_config(
            image_name, "volume", image_params
        )
        volume_id = resmgr.create_resource_object(volume_config)
        config["spec"].update(
            {
                "volume": volume_id,
            }
        )

        return config

    def clone(self):
        LOG.debug(f"Clone the qemu image {self.image_name}")

        config = copy.deepcopy(self.image_config)
        config["spec"].update(
            {
                # No backup for the new image
                "backup": None,
                "volume": resmgr.clone(self.volume_id),
            }
        )

        return self.__class__(config)

    def create_object(self):
        LOG.debug(f"Create the qemu image object for {self.image_name}")
        # volume_config = self.image_spec.pop("volume_config")
        # volume_id = resmgr.create_resource_object(volume_config)
        self.bind_volume(dict())
        resmgr.update_resource(self.volume_id, {"bind": {}})
        # self.image_spec["volume"] = volume_id

    def destroy_object(self):
        LOG.debug(f"Destroy the qemu image object for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"unbind": dict()})
        resmgr.destroy_resource_object(self.volume_id)

    def sync_volume_info(self, arguments):
        LOG.debug(f"Sync up the volume conf for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"sync": arguments})

    def bind_volume(self, arguments):
        LOG.debug(f"Bind the volume {self.volume_id}")
        resmgr.update_resource(self.volume_id, {"bind": arguments})

    def allocate_volume(self, arguments):
        LOG.debug(f"Allocate the volume for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"allocate": arguments})

    def release_volume(self, arguments):
        LOG.debug(f"Release the volume for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"release": arguments})
