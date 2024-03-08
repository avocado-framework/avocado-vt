from .raw_qemu_virt_image import _RawQemuVirtImage
from .qcow2_qemu_virt_image import _Qcow2QemuVirtImage
from .luks_qemu_virt_image import _LuksQemuVirtImage


_image_classes= dict()
_image_classes[_RawQemuVirtImage.get_virt_image_format()] = _RawQemuVirtImage
_image_classes[_Qcow2QemuVirtImage.get_virt_image_format()] = _Qcow2QemuVirtImage
_image_classes[_LuksQemuVirtImage.get_virt_image_format()] = _LuksQemuVirtImage


def get_virt_image_class(virt_image_format):
    return _image_classes.get(virt_image_format)


__all__ = ['get_virt_image_class']
