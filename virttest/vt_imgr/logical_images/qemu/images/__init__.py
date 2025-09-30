from .luks_qemu_image import LuksQemuImage
from .qcow2_qemu_image import Qcow2QemuImage
from .raw_qemu_image import RawQemuImage

_image_classes = dict()
_image_classes[RawQemuImage.IMAGE_FORMAT] = RawQemuImage
_image_classes[Qcow2QemuImage.IMAGE_FORMAT] = Qcow2QemuImage
_image_classes[LuksQemuImage.IMAGE_FORMAT] = LuksQemuImage


def get_qemu_image_class(image_format):
    return _image_classes.get(image_format)


__all__ = ["get_qemu_image_class"]
