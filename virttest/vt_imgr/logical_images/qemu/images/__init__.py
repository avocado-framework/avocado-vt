from .luks_qemu_image import _LuksQemuImage
from .qcow2_qemu_image import _Qcow2QemuImage
from .raw_qemu_image import _RawQemuImage

_image_classes = dict()
_image_classes[_RawQemuImage.get_image_format()] = _RawQemuImage
_image_classes[_Qcow2QemuImage.get_image_format()] = _Qcow2QemuImage
_image_classes[_LuksQemuImage.get_image_format()] = _LuksQemuImage


def get_qemu_image_class(image_format):
    return _image_classes.get(image_format)


__all__ = ["get_qemu_image_class"]
