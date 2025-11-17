from virttest.utils_misc import generate_random_string

from ..qemu_layer_image import QemuLayerImage


class LuksQemuLayerImage(QemuLayerImage):
    IMAGE_FORMAT = "luks"

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        config = super()._define_config_legacy(image_name, image_params)
        spec = config["spec"]
        spec.update(
            {
                "preallocation": image_params.get("preallocated"),
                "extent_size_hint": image_params.get("image_extent_size_hint"),
            }
        )

        name = "secret_{s}".format(s=generate_random_string(6))
        spec["encryption"] = {
            "name": name,
            "data": image_params.get("image_secret", "redhat"),
            "format": image_params.get("image_secret_format", "raw"),
        }

        return config
