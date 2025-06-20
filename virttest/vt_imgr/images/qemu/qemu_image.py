import logging

from virttest.vt_cluster import cluster

from ..image import _Image
from .qemu_virt_image import get_virt_image_class

LOG = logging.getLogger("avocado." + __name__)


class _QemuImage(_Image):

    # The upper-level image type
    _IMAGE_TYPE = "qemu"

    def __init__(self, image_config):
        super().__init__(image_config)
        # Store images with the same order as tags defined in image_chain
        self._handlers.update(
            {
                "create": self.qemu_img_create,
                "destroy": self.qemu_img_destroy,
                "rebase": self.qemu_img_rebase,
                "commit": self.qemu_img_commit,
                "snapshot": self.qemu_img_snapshot,
                "add": self.add_virt_image_object,
                "remove": self.remove_virt_image_object,
                "info": self.qemu_img_info,
                "check": self.qemu_img_check,
                "backup": self.backup,
                "config": self.config,
            }
        )

    @classmethod
    def define_virt_image_config(cls, image_name, image_params):
        image_format = image_params.get("image_format", "qcow2")
        virt_image_class = get_virt_image_class(image_format)
        return virt_image_class.define_config(image_name, image_params)

    @classmethod
    def _define_config_legacy(cls, image_name, params):
        def _define_topo_chain_config():
            backing = None
            for image_tag in image_chain:
                image_params = params.object_params(image_tag)
                virt_images[image_tag] = cls.define_virt_image_config(
                    image_tag, image_params
                )
                if backing is not None:
                    virt_images[image_tag]["spec"]["backing"] = backing
                backing = image_tag

        def _define_topo_none_config():
            image_params = params.object_params(image_name)
            virt_images[image_name] = cls.define_virt_image_config(
                image_name, image_params
            )

        config = super()._define_config_legacy(image_name, params)
        image_params = params.object_params(image_name)
        config["meta"]["user"] = image_params.get(f"image_owner_{image_name}")
        virt_images = config["spec"]["virt-images"]

        # image_chain should be the upper-level image param
        image_chain = params.object_params(image_name).objects("image_chain")
        if image_chain:
            # config["meta"]["topology"] = {"type": "chain", "value": image_chain}
            config["meta"]["topology"] = {"chain": image_chain}
            _define_topo_chain_config()
        else:
            # config["meta"]["topology"] = {"type": "flat", "value": [image_name]}
            config["meta"]["topology"] = {"none": [image_name]}
            _define_topo_none_config()

        return config

    @property
    def image_access_nodes(self):
        node_set = set()
        for virt_image in self.virt_images.values():
            node_set.update(virt_image.virt_image_access_nodes)
        return list(node_set)

    @property
    def virt_images(self):
        return self._virt_images

    @property
    def virt_image_names(self):
        if "none" in self.image_meta["topology"]:
            names = self.image_meta["topology"]["none"]
        elif "chain" in self.image_meta["topology"]:
            names = self.image_meta["topology"]["chain"]
        else:
            raise ValueError("Unknown topology %s" % self.image_meta["topology"])
        return names

    def create_virt_image_object(self, virt_image_name):
        config = self.image_spec["virt-images"][virt_image_name]
        image_format = config["spec"]["format"]
        virt_image_class = get_virt_image_class(image_format)
        virt_image = virt_image_class(config)
        virt_image.create_object()
        return virt_image

    def create_object(self):
        """
        Create the qemu image object.
        All its lower-level virt image objects and their volume
        objects will be created
        """
        LOG.debug("Created the image object for qemu image %s", self.image_meta["name"])
        for virt_image_name in self.virt_image_names:
            self.virt_images[virt_image_name] = self.create_virt_image_object(
                virt_image_name
            )

    def destroy_virt_image_object(self, virt_image_name):
        virt_image = self.virt_images.pop(virt_image_name)
        virt_image.destroy_object()

    def destroy_object(self):
        """
        Destroy the image object, all its lower-level image objects
        will be destroyed.
        """
        for virt_image_name in self.virt_image_names[::-1]:
            self.destroy_virt_image_object(virt_image_name)
        for virt_image_name in self.virt_images:
            self.destroy_virt_image_object(virt_image_name)

    def get_info(self, request):
        for virt_image in self.virt_images.values():
            virt_image.sync_volume(dict())

        config = self.image_config
        if request is not None:
            for item in request.split("."):
                if item in config:
                    config = config[item]
                else:
                    raise ValueError(request)
            else:
                config = {item: config}

        return config

    def add_virt_image_object(self, arguments):
        """
        Add a lower-level virt image into the qemu image

        Create the virt image object
        Update the qemu image's topology

        Note: If the virt image has a backing, then its backing must be
        the topest virt image, e.g. base <-- top, add top1, top1's backing
        must be top, setting top1's backing to base will lead to error.
        """
        target = arguments["target"]
        target_image_params = arguments["target_params"]
        backing_chain = arguments.get("backing_chain", False)
        node_names = arguments.get("nodes") or self.image_access_nodes

        if target in self.virt_images:
            raise ValueError(f"{target} already existed")

        if not set(node_names).issubset(set(self.image_access_nodes)):
            raise ValueError(
                f"{node_names} should be a subset of {self.image_access_nodes}"
            )

        config = self.define_virt_image_config(target, target_image_params)

        if backing_chain:
            config["spec"]["backing"] = self.virt_image_names[-1]
            self.virt_image_names.append(target)
            self.image_meta["name"] = target
            if "none" in self.image_meta["topology"]:
                self.image_meta["topology"]["chain"] = self.image_meta["topology"].pop(
                    "none"
                )

            LOG.info(
                "Qemu image changed: name=%s, topology=%s",
                self.image_meta["name"],
                self.image_meta["topology"],
            )

        self.image_spec["virt-images"][target] = config
        self.virt_images[target] = self.create_virt_image_object(target)

    def remove_virt_image_object(self, arguments):
        """
        Remove the lower-level virt image

        Destroy the virt image object
        Update the qemu image's topology
        """
        target = arguments.pop("target")

        if target not in self.virt_images:
            raise ValueError(f"{target} does not exist")

        if len(self.virt_images) == 1:
            raise ValueError(
                f"Cannot remove {target} for a qemu image "
                "must have at least one lower-level image"
            )

        if target in self.virt_image_names:
            if (
                "chain" in self.image_meta["topology"]
                and target != self.virt_image_names[-1]
            ):
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be removed" % self.virt_image_names
                )
            elif "none" in self.image_meta["topology"]:
                raise ValueError(
                    "Removing %s in topology(%s) can cause an "
                    "unknown state of the image" % (target, self.virt_image_names)
                )

        virt_image = self.virt_images.pop(target)
        if virt_image.volume_allocated:
            raise RuntimeError(f"The resource of {target} isn't released yet")

        virt_image.destroy_object()

        if target in self.virt_image_names:
            self.virt_image_names.remove(target)
            self.image_meta["name"] = self.virt_image_names[-1]

            if len(self.virt_image_names) < 2:
                self.image_meta["topology"]["none"] = self.image_meta["topology"].pop(
                    "chain"
                )

            LOG.info(
                "Qemu image changed: name=%s, topology=%s",
                self.image_meta["name"],
                self.image_meta["topology"],
            )

    def config(self, arguments):
        pass

    def backup(self, arguments):
        """
        Backup the image data

        Backup all lower-level images, or backup a specified one
        """
        target = arguments.pop("target", None)
        image_tags = [target] if target else self.virt_image_names

        for image_tag in image_tags:
            virt_image = self.virt_images[image_tag]

    def qemu_img_create(self, arguments):
        """
        qemu-img create

        Allocate storage
        Create lower-level virt images with qemu-img
        """
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)

        target = arguments.get("target")
        if target in self.virt_image_names:
            if target != self.virt_image_names[-1]:
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be created" % self.virt_image_names
                )

        image_tags = [target] if target else self.virt_image_names
        LOG.info(
            "Create the qemu image %s, targets: %s", self.image_meta["name"], image_tags
        )

        for image_tag in image_tags:
            virt_image = self.virt_images[image_tag]
            virt_image.allocate_volume(arguments)

        r, o = node.proxy.image.handle_image(self.image_config, {"create": arguments})
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_destroy(self, arguments):
        """
        Release the storage

        Note all the lower-level image objects and their volume objects
        will not be destroyed.
        """
        target = arguments.pop("target", None)
        if target in self.virt_image_names:
            if target != self.virt_image_names[-1]:
                raise ValueError(
                    "Only the top virt image in topology(%s) "
                    "can be destroyed" % self.virt_image_names
                )

        image_tags = [target] if target else list(self.virt_images.keys())
        LOG.info(
            "Destroy the qemu image %s, targets: %s",
            self.image_meta["name"],
            image_tags,
        )

        for image_tag in image_tags:
            self.virt_images[image_tag].release_volume(arguments)

    def qemu_img_rebase(self, arguments):
        """
        Rebase target to the top of the qemu image
        """
        target = arguments.get("target")
        backing = self.virt_image_names[-1]
        arguments["source"] = backing

        LOG.info(f"Rebase lower-level image {target} onto {backing}")
        add_args = {
            "target": arguments["target"],
            "target_params": arguments.pop("target_params"),
            "nodes": arguments.pop("nodes", None),
        }
        self.add_virt_image_object(add_args)

        create_args = {
            "target": target,
        }
        self.qemu_img_create(create_args)

        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.handle_image(self.image_config, {"rebase": arguments})
        if r != 0:
            raise Exception(o["out"])

        self.image_meta["name"] = target
        self.virt_image_names.append(target)
        if "none" in self.image_meta["topology"]:
            self.image_meta["topology"]["chain"] = self.image_meta["topology"].pop(
                "none"
            )
        config = self.image_spec["virt-images"][target]
        config["spec"]["backing"] = backing

        LOG.info(
            "Qemu image changed: name=%s, topology=%s",
            self.image_meta["name"],
            self.image_meta["topology"],
        )

    def qemu_img_commit(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.handle_image(self.image_config, {"commit": arguments})
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_snapshot(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.handle_image(self.image_config, {"snapshot": arguments})
        if r != 0:
            raise Exception(o["out"])

    def qemu_img_info(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.handle_image(self.image_config, {"info": arguments})
        if r != 0:
            raise Exception(o["out"])
        return o["out"]

    def qemu_img_check(self, arguments):
        node_name = self.image_access_nodes[0]
        node = cluster.get_node(node_name)
        r, o = node.proxy.image.handle_image(self.image_config, {"check": arguments})
        if r != 0:
            raise Exception(o["out"])
        return o["out"]
