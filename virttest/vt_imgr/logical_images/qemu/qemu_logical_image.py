import copy
import logging

from virttest.utils_misc import generate_random_string
from virttest.vt_cluster import cluster
from virttest.vt_resmgr import resmgr

from ..logical_image import _LogicalImage
from .images import get_qemu_image_class

LOG = logging.getLogger("avocado." + __name__)


class _QemuLogicalImage(_LogicalImage):

    _IMAGE_TYPE = "qemu"

    def __init__(self, image_config):
        super().__init__(image_config)
        self._handlers.update(
            {
                "rebase": self.qemu_img_rebase,
                "commit": self.qemu_img_commit,
                "snapshot": self.qemu_img_snapshot,
                "add": self.add_image_object,
                "remove": self.remove_image_object,
                "info": self.qemu_img_info,
                "check": self.qemu_img_check,
            }
        )

    @classmethod
    def define_image_config(cls, image_name, image_params):
        image_format = image_params.get("image_format", "qcow2")
        image_class = get_qemu_image_class(image_format)
        return image_class.define_config(image_name, image_params)

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        def _define_topo_chain_config():
            for image_tag in image_chain:
                image_params = params.object_params(image_tag)
                images[image_tag] = cls.define_image_config(image_tag, image_params)

        def _define_topo_flat_config():
            image_params = params.object_params(image_name)
            images[image_name] = cls.define_image_config(image_name, image_params)

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

    @property
    def image_access_nodes(self):
        """
        Get the nodes where all images can be accessed
        """
        node_set = set()
        for image in self.images.values():
            node_set.update(image.image_access_nodes)
        return list(node_set)

    @property
    def image_names(self):
        return self.image_meta["topology"]["value"]

    def _create_image_object(self, image_name):
        config = self.image_spec["images"][image_name]
        image_format = config["spec"]["format"]
        image_class = get_qemu_image_class(image_format)
        image = image_class(config)
        image.create_object()
        return image

    def create_object(self):
        """
        Create the qemu logical image object.
        All its lower-level image objects objects will be created
        """
        LOG.debug("Created the qemu image object for %s", self.image_name)
        for image_name in self.image_names:
            self.images[image_name] = self._create_image_object(image_name)

    def _destroy_image_object(self, image_name):
        image = self.images.pop(image_name)
        image.destroy_object()

    def destroy_object(self):
        """
        Destroy the image object, all its lower-level image objects
        will be destroyed.
        """
        for image_name in self.image_names[::-1]:
            self._destroy_image_object(image_name)
        for image_name in self.images:
            self._destroy_image_object(image_name)

    def add_image_object(self, arguments):
        """
        Add a new lower-level qemu image into the logical image
        """
        image_name = arguments["target"]
        image_params = arguments.pop("target_params")
        node_names = arguments.pop("nodes", self.image_access_nodes)

        if image_name in self.images:
            raise ValueError(f"{image_name} already existed")

        if not set(node_names).issubset(set(self.image_access_nodes)):
            raise ValueError(
                f"{node_names} should be a subset of {self.image_access_nodes}"
            )

        self.image_spec["images"][image_name]  = self.define_image_config(image_name, image_params)
        self.images[image_name] = self._create_image_object(image_name)

    def remove_image_object(self, arguments):
        """
        Remove the lower-level qemu image

        Destroy the virt image object
        Update the qemu image's topology
        """
        target = arguments.pop("target")

        if target not in self.images:
            raise ValueError(f"{target} does not exist")

        if len(self.images) == 1:
            raise ValueError(
                f"Cannot remove {target} for a qemu image "
                "must have at least one lower-level image"
            )

        if target in self.image_names:
            if (
                "chain" == self.image_meta["topology"]["type"]
                and target != self.image_names[-1]
            ):
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be removed" % self.image_names
                )
            elif "flat" == self.image_meta["topology"]["type"]:
                raise ValueError(
                    "Removing %s in topology(%s) can cause an "
                    "unknown state of the image" % (target, self.image_names)
                )

        image = self.images.pop(target)
        if image.volume_allocated:
            raise RuntimeError(f"The resource of {target} isn't released yet")

        image.destroy_object()

        if target in self.image_names:
            self.image_names.remove(target)
            self.image_meta["name"] = self.image_names[-1]

            if len(self.image_names) == 1:
                self.image_meta["topology"]["type"] = "flat"

            LOG.info(
                "Qemu image changed: name=%s, topology=%s",
                self.image_meta["name"],
                self.image_meta["topology"],
            )

    def clone(self):
        LOG.debug(f"Clone a new logical qemu image based on {self.image_name}")
        config = {
            "meta": copy.deepcopy(self.image_meta),
            "spec": {
                "images": {},
            },
        }

        # Change the image name
        postfix = generate_random_string(8)
        config["meta"]["name"] = f"{self.image_name}_clone_{postfix}"

        # Clone each lower-level image object
        images = dict()
        for image_name in self.image_names:
            image = self.images[image_name]
            cloned_image = image.clone()
            images[image_name] = cloned_image
            config["spec"]["images"][image_name] = cloned_image.image_config

        # Add each image object for management
        obj = self.__class__(config)
        obj._images = images

        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.clone_logical_image(
            self.get_info(verbose=True),
            obj.get_info(verbose=True)
        )
        if r != 0:
            raise Exception(o["out"])

        return obj

    def create(self, arguments):
        """
        Create the image
        """
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)

        target = arguments.get("target")
        if target in self.image_names:
            if target != self.image_names[-1]:
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be created" % self.image_names
                )

        image_tags = [target] if target else self.image_names
        LOG.info(
            "Create the qemu image %s, targets: %s", self.image_meta["name"], image_tags
        )

        # Allocate volume before the qemu image creation even qemu-img command
        # can allocate it, let the resource manager manage the volume resource
        for image_tag in image_tags:
            self.images[image_tag].allocate_volume(arguments)

        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"create": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

    def destroy(self, arguments):
        """
        Destroy the image

        Note all the lower-level image objects and their volume objects
        will not be destroyed.
        """
        target = arguments.pop("target", None)
        if target in self.image_names:
            if target != self.image_names[-1]:
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be destroyed" % self.image_names
                )

        image_tags = [target] if target else list(self.images.keys())
        LOG.info(
            "Destroy the qemu image %s, targets: %s",
            self.image_meta["name"],
            image_tags,
        )

        for image_tag in image_tags:
            self.images[image_tag].release_volume(arguments)

    def backup(self, arguments):
        target = arguments.get("target")
        if target and target not in self.images:
            raise ValueError(f"{target} does not exist")
        image_names = [target] if target else self.image_names

        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)

        # Use the local dir pool to store the backup
        pool_id = None
        for pool_id in resmgr.pools:
            pool_config = resmgr.get_pool_info(pool_id, "meta")
            pool_meta = pool_config["meta"]
            if pool_meta["type"] == "filesystem" and node_name in pool_meta["access"]["nodes"]:
                break

        # For each image, create a new one to store the data
        for image_name in image_names:
            image = self.images[image_name]
            backup_image = image.create_object_by_self(pool_id, [node.tag])
            backup_image.allocate_volume(dict())
            image.image_spec["backup"] = backup_image.image_name
            self.images[backup_image.image_name] = backup_image

        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"backup": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

    def restore(self, arguments):
        target = arguments.get("target")
        if target and target not in self.images:
            raise ValueError(f"{target} does not exist")
        image_names = [target] if target else self.image_names
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)

        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"restore": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        # Remove the backup images
        for image_name in image_names:
            image = self.images[image_name]
            backup_image_name = image.image_spec["backup"]
            backup_image = self.images.pop(backup_image_name)
            backup_image.release_volume(dict())
            self._destroy_image_object(backup_image_name)
            image.image_spec["backup"] = None

    def qemu_img_rebase(self, arguments):
        """
        Rebase target to the top of the qemu image
        """
        LOG.info(f"Rebase qemu image {target} onto {backing}")
        target = arguments["target"]
        if target in self.image_names:
            raise ValueError(f"{target} already existed in the topology")
        if target not in self.images:
            raise ValueError(f"{target} object doesn't exist")

        backing = self.image_names[-1]
        arguments["source"] = backing

        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"rebase": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

        self.image_meta["name"] = target
        self.image_names.append(target)
        if "flat" == self.image_meta["topology"]:
            self.image_meta["topology"]["type"] = "chain"

        LOG.info(
            "The logical qemu image is updated: name=%s, topology=%s",
            self.image_meta["name"],
            self.image_meta["topology"],
        )

    def qemu_img_commit(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"commit": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_snapshot(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"snapshot": arguments}
        )
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_info(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"info": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        return o["out"]

    def qemu_img_check(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.update_logical_image(
            self.get_info(verbose=True), {"check": arguments}
        )
        if r != 0:
            raise Exception(o["out"])
        return o["out"]
