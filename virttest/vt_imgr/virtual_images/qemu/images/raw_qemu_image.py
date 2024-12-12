from ..qemu_image import _QemuImage


class _RawQemuImage(_QemuImage):

    _IMAGE_FORMAT = "raw"

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

        return config
