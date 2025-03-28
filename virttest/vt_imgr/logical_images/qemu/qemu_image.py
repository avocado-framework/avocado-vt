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

        # Store the volume config temporarily, don't create the volume object
        # here, because we'll move the function to a parser used to translate
        # cartesian params into vt configurations
        config["spec"].update(
            {
                "backing": None,
                "volume_config": volume_config,
            }
        )

        return config

    def create_object_from_self(self, pool_id=None):
        LOG.debug(f"Create a new qemu image object based on {self.image_name}")

        config = copy.deepcopy(self.image_config)
        config["spec"].update(
            {
                # The top-level image takes care of the topology
                "backing": None,
                # No backup for the new image
                "backup": None,
                "volume": resmgr.create_resource_object_from(self.volume_id),
            }
        )

        obj = self.__class__(config)

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
