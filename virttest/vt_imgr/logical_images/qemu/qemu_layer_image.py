import logging

from virttest.vt_resmgr import resmgr

from ..layer_image import LayerImage

LOG = logging.getLogger("avocado." + __name__)


class QemuLayerImage(LayerImage):
    """
    The qemu layer image
    """

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        LOG.debug(f"Convert cartesian params to {image_name}'s config in legacy way")

        config = super()._define_config_legacy(image_name, image_params)
        config["meta"].update(
            {
                "raw": image_params.get_boolean("image_raw_device", False),
            }
        )
        config["spec"].update(
            {
                "volume": resmgr.create_resource_from_params(
                    image_name, "volume", image_params
                ),
            }
        )

        return config

    def define_config_by_self(self):
        config = super().define_config_by_self()
        config["meta"].update(
            {
                # Reset its value to False, depend on the user's scenario
                "raw": False,
            }
        )
        return config
