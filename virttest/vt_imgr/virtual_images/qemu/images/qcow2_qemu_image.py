import os

from virttest.data_dir import get_tmp_dir
from virttest.utils_misc import generate_random_string

from ..qemu_image import _QemuImage


class _Qcow2QemuImage(_QemuImage):

    _IMAGE_FORMAT = "qcow2"

    @classmethod
    def _define_config_legacy(cls, image_name, image_params):
        config = super()._define_config_legacy(image_name, image_params)
        spec = config["spec"]
        spec.update(
            {
                "cluster-size": image_params.get("image_cluster_size"),
                "lazy-refcounts": image_params.get("lazy_refcounts"),
                "compat": image_params.get("qcow2_compatible"),
                "preallocation": image_params.get("preallocated"),
                "extent_size_hint": image_params.get("image_extent_size_hint"),
                "compression_type": image_params.get("image_compression_type"),
            }
        )

        name = "secret_{s}".format(s=generate_random_string(6))
        if image_params.get("image_encryption"):
            spec["encryption"] = {
                "name": name,
                "data": image_params.get("image_secret", "redhat"),
                "format": image_params.get("image_secret_format", "raw"),
                "encrypt": {
                    "format": image_params.get("image_encryption", "luks"),
                },
            }

            if image_params.get("image_secret_storage", "data") == "file":
                spec["encryption"]["file"] = os.path.join(get_tmp_dir(), name)

        return config
