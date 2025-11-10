import copy
import logging

from virttest.utils_misc import generate_random_string

from ..logical_image import LogicalImage
from .images import get_qemu_image_class

LOG = logging.getLogger("avocado." + __name__)


class QemuLogicalImage(LogicalImage):
    """
    The qemu logical image class.
    """

    IMAGE_TYPE = "qemu"

    def __init__(self, image_config):
        super().__init__(image_config)
        self._handlers.update(
            {
                "rebase": self.qemu_img_rebase,
                "commit": self.qemu_img_commit,
                "snapshot": self.qemu_img_snapshot,
                "info": self.qemu_img_info,
                "check": self.qemu_img_check,
            }
        )

    @classmethod
    def define_layer_image_config(cls, image_name, image_params):
        image_format = image_params.get("image_format", "qcow2")
        image_class = get_qemu_image_class(image_format)
        return image_class.define_config(image_name, image_params)

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        def _define_topo_chain_config():
            for image_tag in image_chain:
                image_params = params.object_params(image_tag)
                images[image_tag] = cls.define_layer_image_config(
                    image_tag, image_params
                )

        def _define_topo_flat_config():
            image_params = params.object_params(image_name)
            images[image_name] = cls.define_layer_image_config(image_name, image_params)

        config = super()._define_config_legacy(image_name, params)
        images = config["spec"]["images"]

        # image_chain should be the logical image param
        image_chain = params.object_params(image_name).get_list("image_chain")
        if image_chain:
            config["meta"]["topology"] = {"type": "chain", "value": image_chain}
            _define_topo_chain_config()
        else:
            config["meta"]["topology"] = {"type": "flat", "value": [image_name]}
            _define_topo_flat_config()

        return config

    def define_config_by_self(self):
        config = {
            "meta": copy.deepcopy(self.meta),
            "spec": {
                "images": dict(),
            },
        }
        topo_names = config["meta"]["topology"]["value"]

        for image_name in self.topo_layer_image_names:
            layer_image = self.layer_images[image_name]
            layer_image_config = layer_image.define_config_by_self()
            layer_image_name = layer_image_config["meta"]["name"]
            # Update the layer image name
            config["spec"]["images"][layer_image_name] = layer_image_config
            # Update the topology layer image name list
            idx = topo_names.index(image_name)
            topo_names[idx] = layer_image_name

        postfix = generate_random_string(8)
        logical_image_name = f"{self.name}_{postfix}"
        config["meta"].update(
            {
                "uuid": None,
                "name": logical_image_name,
            }
        )
        return config

    def _create_layer_image_object(self, layer_image_name):
        config = self.spec["images"][layer_image_name]
        image_format = config["spec"]["format"]
        image_class = get_qemu_image_class(image_format)
        return image_class(config)

    def create_layer_images(self):
        for image_name in self.topo_layer_image_names:
            self.layer_images[image_name] = self._create_layer_image_object(image_name)

    def clone(self, arguments, node):
        config = self.define_config_by_self()
        config["spec"]["images"].clear()
        topo_names = config["meta"]["topology"]["value"]
        cloned_image = self.__class__(config)

        # Clone each layer image object
        for idx in range(len(self.topo_layer_image_names)):
            image_name = self.topo_layer_image_names[idx]
            image = self.layer_images[image_name]
            clone = image.clone(arguments, node)
            cloned_image.layer_images[clone.name] = clone
            # Reset the layer image's configuration
            cloned_image.spec["images"][clone.name] = clone.config
            # Update the topology layer image name list
            topo_names[idx] = clone.name
            idx += 1

        r, o = node.proxy.image.clone_logical_image(
            self.customized_config(), cloned_image.customized_config()
        )
        if r != 0:
            raise Exception(o["out"])

        return cloned_image

    def create(self, arguments, node):
        """
        Create the qemu logical image on a specified node.
        If "target" image has backing and the backing is not created, then
        create the backing image first.
        """
        image_tags = self.topo_layer_image_names
        target = arguments.get("target")
        if target:
            if target not in self.layer_images:
                raise ValueError(
                    f"{target} layer image object doesn't exist in {self.name}."
                )
            elif target in self.topo_layer_image_names:
                idx = self.topo_layer_image_names.index(target)
                image_tags = self.topo_layer_image_names.index[: idx + 1]
            else:
                image_tags = [target]

        image_tags = [
            t for t in image_tags if not self.layer_images[t].volume_allocated
        ]
        if not image_tags:
            raise RuntimeError("All layer images have already been created.")

        # Allocate volume before the qemu image creation even qemu-img command
        # can allocate it, let the resource manager manage the storage.
        for image_tag in image_tags:
            self.layer_images[image_tag].allocate_volume(arguments, node)

        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "create", arguments
        )
        if r != 0:
            raise Exception(o["out"])

    def destroy(self, arguments, node):
        """
        Destroy the qemu logical image.
        If the "target" has a snapshot image, then destroy the snapshot first.

        Note the layer image objects and their volume objects and their
        backing objects will not be destroyed.
        """
        image_tags = self.topo_layer_image_names
        target = arguments.get("target")
        if target:
            if target not in self.layer_images:
                raise ValueError(
                    f"{target} layer image object doesn't exist in {self.name}."
                )
            elif target in self.topo_layer_image_names:
                idx = self.topo_layer_image_names.index(target)
                image_tags = self.topo_layer_image_names.index[idx:]
            else:
                image_tags = [target]

        image_tags = [t for t in image_tags if self.layer_images[t].volume_allocated]
        if not image_tags:
            raise RuntimeError("All layer images have already been destroyed.")

        for image_tag in image_tags[::-1]:
            self.layer_images[image_tag].release_volume(arguments, node)

    def backup(self, arguments, node):
        target = arguments.get("target")
        if target and target not in self.layer_images:
            raise ValueError(f"Layer image {target} does not exist")
        image_names = [target] if target else self.topo_layer_image_names

        # For each image, create a new one to store the data
        for image_name in image_names:
            layer_image = self.layer_images[image_name]
            backup_image = layer_image.create_backup_image(arguments, node)
            self.layer_images[backup_image.name] = backup_image
            # Update the logical layer images' config
            self.spec["images"][backup_image.name] = backup_image.config

        # Backup the data
        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "backup", arguments
        )
        if r != 0:
            raise Exception(o["out"])

    def restore(self, arguments, node):
        target = arguments.get("target")
        if target and target not in self.layer_images:
            raise ValueError(f"Layer image {target} does not exist")
        image_names = [target] if target else self.topo_layer_image_names

        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "restore", arguments
        )
        if r != 0:
            raise Exception(o["out"])

        for image_name in image_names:
            layer_image = self.layer_images[image_name]
            backup_image_name = layer_image.spec["backup"]
            # Remove backup image from layer images
            backup_image = self.layer_images.pop(backup_image_name)
            backup_image.release_volume(arguments, node)
            # Remove all backings
            backup_image.unbind_volume()
            # Remove backup image config from logical image's config
            self.spec["images"].pop(backup_image_name)
            # Reset layer image's backup to None
            layer_image.spec["backup"] = None

    def qemu_img_rebase(self, arguments, node):
        """
        Rebase target to the top of the qemu image
        """
        target = arguments["target"]
        if target in self.topo_layer_image_names:
            raise ValueError(f"{target} already existed in the topology")
        if target not in self.layer_images:
            raise ValueError(f"{target} object doesn't exist")

        backing = self.topo_layer_image_names[-1]
        arguments["source"] = backing

        LOG.info(f"Rebase qemu image {target} onto {backing}")
        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "rebase", arguments
        )
        if r != 0:
            raise Exception(o["out"])

        self.meta["name"] = target
        self.topo_layer_image_names.append(target)
        if "flat" == self.meta["topology"]:
            self.meta["topology"]["type"] = "chain"

        LOG.info(
            "The logical qemu image is updated: name=%s, topology=%s",
            self.meta["name"],
            self.meta["topology"],
        )

    def qemu_img_commit(self, arguments, node):
        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "commit", arguments
        )
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_snapshot(self, arguments, node):
        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "snapshot", arguments
        )
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_info(self, arguments, node):
        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "info", arguments
        )
        if r != 0:
            raise Exception(o["out"])
        return o["out"]

    def qemu_img_check(self, arguments, node):
        r, o = node.proxy.image.update_logical_image(
            self.customized_config(), "check", arguments
        )
        if r != 0:
            raise Exception(o["out"])
        return o["out"]
