from .luks_qemu_layer_image import LuksQemuLayerImage
from .qcow2_qemu_layer_image import Qcow2QemuLayerImage
from .raw_qemu_layer_image import RawQemuLayerImage

_image_classes = dict()
_image_classes[RawQemuLayerImage.IMAGE_FORMAT] = RawQemuLayerImage
_image_classes[Qcow2QemuLayerImage.IMAGE_FORMAT] = Qcow2QemuLayerImage
_image_classes[LuksQemuLayerImage.IMAGE_FORMAT] = LuksQemuLayerImage


def get_qemu_image_class(image_format):
    return _image_classes.get(image_format)


__all__ = ["get_qemu_image_class"]
