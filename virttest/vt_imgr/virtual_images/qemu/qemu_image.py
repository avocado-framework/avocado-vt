import copy
import logging

from virttest.vt_resmgr import resmgr

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
        config["spec"].update(
            {
                "backing": None,
                "volume_config": volume_config,
            }
        )

        return config

    def keep(self):
        pass

    def clone(self):
        LOG.debug(f"Clone the qemu image object from {self.image_name}")

        # FIXME: Copy the data to the new storage
        config = copy.deepcopy(self.image_config)
        config["spec"]["volume"] = resmgr.clone_resource(self.volume_id)
        return self.__class__(config)

    def create_object(self):
        LOG.debug(f"Create the qemu image object for {self.image_name}")
        volume_config = self.image_spec.pop("volume_config")
        volume_id = resmgr.create_resource_object(volume_config)
        self.image_spec["volume"] = volume_id
        resmgr.update_resource(volume_id, {"bind": dict()})

    def destroy_object(self):
        LOG.debug(f"Destroy the qemu image object for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"unbind": dict()})
        resmgr.destroy_resource_object(self.volume_id)

    def sync_volume_info(self, arguments):
        LOG.debug(f"Sync up the volume conf for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"sync": arguments})

    def allocate_volume(self, arguments):
        LOG.debug(f"Allocate the volume for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"allocate": arguments})

    def release_volume(self, arguments):
        LOG.debug(f"Release the volume for {self.image_name}")
        resmgr.update_resource(self.volume_id, {"release": arguments})
